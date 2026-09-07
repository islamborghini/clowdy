"""
Scheduler -- decides which worker runs an invocation.

AWS Lambda equivalent: the placement half of the Worker Manager.

The naive answer is round-robin, and it is wrong here. Every worker keeps its
own warm container pool keyed by (image, network), so where a request lands
changes whether it is a 20ms warm exec or a 700ms cold start. Round-robin
spreads the same image across every worker and turns N warm pools into N cold
starts. Sticky-by-hash fixes that but creates hot spots: one popular image
pins all its traffic to one node while the rest idle.

So this uses consistent hashing with bounded loads (Mirsky et al., the
algorithm behind Google's load balancer and HAProxy's `balance hash` with
`hash-balance-factor`): hash the pool key onto a ring for warm affinity, then
walk the ring forward past any node already carrying more than its fair share.
Affinity when there is room, spillover when there is not.

The ring is rebuilt on every scheduling decision. That is O(workers * vnodes)
per invoke, which for a fleet of tens is a few microseconds and saves keeping
a mutable ring correct across membership changes in every replica.
"""

import bisect
import hashlib
import math

from app.services.registry import WorkerInfo

# Virtual nodes per worker. Higher means a more even key distribution and a
# smaller share of keys remapped when a worker joins or leaves.
VNODES = 64

# How far above the fleet average a worker may go before the ring walks past
# it. 1.25 means "up to 25 percent more than its fair share". Lower is more
# even but breaks warm affinity sooner; higher keeps affinity but tolerates
# hot spots. 1.25 is HAProxy's suggested starting point.
BALANCE_FACTOR = 1.25


def _hash(value: str) -> int:
    """Stable 64-bit hash. md5 is not for security here, just for spread."""
    return int(hashlib.md5(value.encode()).hexdigest()[:16], 16)


class HashRing:
    """A consistent hash ring over worker IDs."""

    def __init__(self, worker_ids: list[str], vnodes: int = VNODES):
        self._ring: list[tuple[int, str]] = sorted(
            (_hash(f"{wid}#{i}"), wid) for wid in worker_ids for i in range(vnodes)
        )
        self._points = [point for point, _ in self._ring]

    def ordered(self, key: str) -> list[str]:
        """
        Worker IDs in ring order starting at the key's position.

        The first entry is the key's preferred (warm) home. The rest are the
        fallback order, used both for load spillover and for retry after a
        worker fails.
        """
        if not self._ring:
            return []

        start = bisect.bisect(self._points, _hash(key))
        seen: list[str] = []
        for offset in range(len(self._ring)):
            _, worker_id = self._ring[(start + offset) % len(self._ring)]
            if worker_id not in seen:
                seen.append(worker_id)
        return seen


def pool_key(image: str, network_enabled: bool) -> str:
    """
    The affinity key for an invocation.

    Deliberately NOT the function ID. Warm containers are reusable across any
    function sharing an image and network setting -- code is injected at exec
    time -- so hashing on the image is what actually maximises warm hits.
    """
    return f"{image}|net={int(network_enabled)}"


def plan(workers: list[WorkerInfo], key: str) -> list[WorkerInfo]:
    """
    Order the fleet for one invocation: best worker first, then failover order.

    Returns an empty list when every worker is at capacity, which the caller
    surfaces as a 503 rather than queueing unboundedly.
    """
    if not workers:
        return []

    by_id = {w.id: w for w in workers if w.inflight < w.capacity}
    if not by_id:
        return []
    available = list(by_id.values())

    # The ring is built over the WHOLE fleet, not just the workers with room.
    # Ring membership must track which workers exist, not which are momentarily
    # busy -- otherwise every load fluctuation reshuffles the ring, affinity
    # churns, and the warm pools the ring exists to protect go cold.
    # Saturated workers are skipped during the walk instead.
    ring_order = [
        by_id[wid] for wid in HashRing([w.id for w in workers]).ordered(key) if wid in by_id
    ]

    # Bounded load: the cap is the fleet average plus the balance factor's
    # slack, floored at 1 so an idle fleet still honours affinity.
    total_inflight = sum(w.inflight for w in available)
    cap = max(1, math.ceil((total_inflight / len(available)) * BALANCE_FACTOR))

    primary = next((w for w in ring_order if w.inflight < cap), None)
    if primary is None:
        # Every node is above the cap (they are all equally hot). Fall back to
        # plain least-outstanding-requests.
        primary = min(available, key=lambda w: (w.inflight, w.id))

    rest = sorted(
        (w for w in ring_order if w.id != primary.id),
        key=lambda w: (w.inflight, w.id),
    )
    return [primary] + rest
