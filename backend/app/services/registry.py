"""
Worker registry -- the shared view of which data-plane nodes exist right now.

AWS Lambda equivalent: the Worker Manager's fleet state.

Every worker writes a heartbeat key into Redis with a short TTL. The control
plane reads those keys to decide where to place an invocation. Nothing ever
deletes a dead worker: its key simply expires, and it falls out of the ring
on the next read. That is the whole failure detector -- no gossip, no leader
election, no consensus, because the cost of routing one invocation to a node
that died 3 seconds ago is a single retry.

Redis is optional. With REDIS_URL unset the registry reports itself disabled
and the dispatcher executes locally instead, so `uvicorn app.main:app` on a
laptop still works with no cluster at all.
"""

import json
import logging
import time
from dataclasses import asdict, dataclass

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

WORKER_KEY_PREFIX = "clowdy:worker:"
INFLIGHT_KEY_PREFIX = "clowdy:inflight:"

# How long an in-flight counter survives without being decremented. This is a
# leak bound, not a timeout: if a control-plane replica dies mid-dispatch its
# increment would otherwise mark a healthy worker busy forever.
INFLIGHT_TTL_SECONDS = 120


@dataclass
class WorkerInfo:
    """One data-plane node as advertised in its most recent heartbeat."""

    id: str
    url: str
    capacity: int
    warm_containers: int = 0
    invocations: int = 0
    cold_starts: int = 0
    started_at: float = 0.0
    # Filled in by the registry on read, not written by the worker itself.
    inflight: int = 0

    @property
    def uptime_seconds(self) -> float:
        """Seconds since this worker booted. Zero if it never reported one."""
        return time.time() - self.started_at if self.started_at else 0.0

    @property
    def load(self) -> float:
        """Fraction of capacity currently in use. Used to break hash ties."""
        return self.inflight / self.capacity if self.capacity else 1.0


class WorkerRegistry:
    """Redis-backed fleet state. Safe to use when Redis is absent (disabled)."""

    def __init__(self, redis_url: str, ttl_seconds: int = 15):
        self.redis_url = redis_url
        self.ttl = ttl_seconds
        self._redis: aioredis.Redis | None = None

    @property
    def enabled(self) -> bool:
        return bool(self.redis_url)

    async def connect(self) -> None:
        if not self.enabled:
            logger.info("No REDIS_URL set -- running single-node, local execution only")
            return
        self._redis = aioredis.from_url(self.redis_url, decode_responses=True)
        await self._redis.ping()
        logger.info("Connected to Redis at %s", self.redis_url)

    async def aclose(self) -> None:
        if self._redis is not None:
            await self._redis.aclose()
            self._redis = None

    async def heartbeat(self, worker: WorkerInfo) -> None:
        """Publish this worker's liveness and stats. Called on a timer."""
        if self._redis is None:
            return
        payload = asdict(worker)
        payload.pop("inflight", None)  # read-side field, not the worker's to set
        await self._redis.set(
            WORKER_KEY_PREFIX + worker.id, json.dumps(payload), ex=self.ttl
        )

    async def deregister(self, worker_id: str) -> None:
        """Remove a worker immediately on graceful shutdown."""
        if self._redis is None:
            return
        await self._redis.delete(WORKER_KEY_PREFIX + worker_id)

    async def list_workers(self) -> list[WorkerInfo]:
        """Every worker whose heartbeat has not yet expired, with live load."""
        if self._redis is None:
            return []

        keys = [key async for key in self._redis.scan_iter(match=WORKER_KEY_PREFIX + "*")]
        if not keys:
            return []

        raw_workers = await self._redis.mget(keys)
        workers = []
        for raw in raw_workers:
            if not raw:
                continue  # expired between the scan and the mget
            try:
                workers.append(WorkerInfo(**json.loads(raw)))
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning("Skipping malformed worker entry: %s", exc)

        if not workers:
            return []

        counts = await self._redis.mget(
            [INFLIGHT_KEY_PREFIX + w.id for w in workers]
        )
        for worker, count in zip(workers, counts):
            worker.inflight = max(0, int(count or 0))

        return sorted(workers, key=lambda w: w.id)

    async def acquire_slot(self, worker_id: str) -> None:
        """Mark one invocation as in flight on a worker."""
        if self._redis is None:
            return
        key = INFLIGHT_KEY_PREFIX + worker_id
        async with self._redis.pipeline() as pipe:
            await pipe.incr(key).expire(key, INFLIGHT_TTL_SECONDS).execute()

    async def release_slot(self, worker_id: str) -> None:
        """Release an in-flight slot. Never lets the counter go negative."""
        if self._redis is None:
            return
        key = INFLIGHT_KEY_PREFIX + worker_id
        value = await self._redis.decr(key)
        if value < 0:
            await self._redis.set(key, 0, ex=INFLIGHT_TTL_SECONDS)


def new_worker_info(worker_id: str, url: str, capacity: int) -> WorkerInfo:
    """Build the heartbeat record for the worker running in this process."""
    return WorkerInfo(id=worker_id, url=url, capacity=capacity, started_at=time.time())
