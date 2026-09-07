"""
Tests for placement: the part of the platform where a plausible-looking
implementation silently costs you every warm container.
"""

from app.services.registry import WorkerInfo
from app.services.scheduler import HashRing, plan, pool_key


def fleet(*specs: tuple[str, int, int]) -> list[WorkerInfo]:
    """Build a fleet from (id, inflight, capacity) triples."""
    return [
        WorkerInfo(id=wid, url=f"http://{wid}:9000", capacity=cap, inflight=inflight)
        for wid, inflight, cap in specs
    ]


def test_affinity_is_stable_for_the_same_pool_key():
    """The same image must land on the same worker, or warm pools never hit."""
    workers = fleet(("w1", 0, 8), ("w2", 0, 8), ("w3", 0, 8))
    key = pool_key("clowdy-python-runtime", False)
    first = plan(workers, key)[0].id
    assert all(plan(workers, key)[0].id == first for _ in range(20))


def test_different_images_spread_across_the_fleet():
    """Affinity must not collapse the whole fleet onto one node."""
    workers = fleet(("w1", 0, 8), ("w2", 0, 8), ("w3", 0, 8))
    chosen = {
        plan(workers, pool_key(f"image-{i}", False))[0].id for i in range(60)
    }
    assert len(chosen) == 3


def test_bounded_load_spills_off_a_hot_worker():
    """
    Pure consistent hashing would keep sending work to its preferred node.
    Bounded load must walk past a node carrying more than its fair share.
    """
    key = pool_key("clowdy-python-runtime", False)
    idle = fleet(("w1", 0, 8), ("w2", 0, 8), ("w3", 0, 8))
    preferred = plan(idle, key)[0].id

    hot = fleet(
        *[
            (w.id, 7 if w.id == preferred else 0, 8)
            for w in idle
        ]
    )
    assert plan(hot, key)[0].id != preferred


def test_full_workers_are_never_chosen():
    workers = fleet(("w1", 8, 8), ("w2", 3, 8), ("w3", 8, 8))
    assert [w.id for w in plan(workers, "k")] == ["w2"]


def test_saturated_fleet_returns_no_placement():
    """An empty plan is what the dispatcher turns into a 503 instead of a queue."""
    assert plan(fleet(("w1", 8, 8), ("w2", 8, 8)), "k") == []


def test_plan_includes_failover_order():
    """Every healthy worker appears, so a failed dispatch has somewhere to go."""
    workers = fleet(("w1", 1, 8), ("w2", 0, 8), ("w3", 2, 8))
    ordered = plan(workers, "k")
    assert len(ordered) == 3
    assert len({w.id for w in ordered}) == 3
    # Fallbacks after the primary are ordered least-loaded first.
    fallback_loads = [w.inflight for w in ordered[1:]]
    assert fallback_loads == sorted(fallback_loads)


def test_removing_a_worker_does_not_reshuffle_the_others():
    """
    The reason for consistent hashing rather than `hash(key) % n`: removing a
    node must only remap the keys that node owned. With modulo, every key
    moves and the whole fleet cold-starts at once.
    """
    keys = [f"image-{i}" for i in range(600)]
    before = HashRing(["w1", "w2", "w3"])
    after = HashRing(["w1", "w2"])

    moved = sum(
        1
        for k in keys
        if before.ordered(k)[0] != "w3" and before.ordered(k)[0] != after.ordered(k)[0]
    )
    assert moved == 0, "keys not homed on the departed worker must not move"


def test_network_setting_is_part_of_the_affinity_key():
    """A networked container cannot serve a no-network invocation."""
    assert pool_key("img", True) != pool_key("img", False)


def test_a_busy_worker_does_not_reshuffle_the_ring():
    """
    Ring membership tracks which workers exist, not which are momentarily
    busy. If a saturated worker fell out of the ring, every load fluctuation
    would remap keys and cold-start the fleet.
    """
    key = pool_key("clowdy-python-runtime", False)
    idle = fleet(("w1", 0, 8), ("w2", 0, 8), ("w3", 0, 8))
    order_when_idle = [w.id for w in plan(idle, key)]

    # Saturate whichever worker is second in line. The first choice must not
    # change, and neither must the relative ring position of the others.
    busy_id = order_when_idle[1]
    busy = fleet(*[(w.id, 8 if w.id == busy_id else 0, 8) for w in idle])

    assert plan(busy, key)[0].id == order_when_idle[0]
    assert busy_id not in [w.id for w in plan(busy, key)]


def test_partial_capacity_still_yields_candidates():
    """
    A fleet where most workers are full is not a saturated fleet. Only an
    empty plan means throttle; anything else must still be dispatched.
    """
    workers = fleet(("w1", 8, 8), ("w2", 8, 8), ("w3", 7, 8))
    assert [w.id for w in plan(workers, "k")] == ["w3"]
