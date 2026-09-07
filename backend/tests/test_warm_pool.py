"""Tests for the warm container pool: reuse, LRU eviction, and idle reaping."""

import time

from app.services.assignment_service import AssignmentService


class FakeContainer:
    """Stands in for a Docker container. Records whether it was destroyed."""

    def __init__(self, name: str):
        self.name = name
        self.removed = False

    def remove(self, force: bool = False):
        self.removed = True


def test_release_then_acquire_reuses_the_same_container():
    pool = AssignmentService(max_pool_size=4)
    container = FakeContainer("c1")
    pool.release(container, "img", False)
    assert pool.acquire("img", False) is container


def test_acquire_misses_on_a_different_pool_key():
    pool = AssignmentService(max_pool_size=4)
    pool.release(FakeContainer("c1"), "img", False)
    assert pool.acquire("img", True) is None
    assert pool.acquire("other-img", False) is None


def test_full_pool_evicts_the_least_recently_used():
    pool = AssignmentService(max_pool_size=2)
    oldest = FakeContainer("oldest")
    pool.release(oldest, "img", False)
    time.sleep(0.01)
    pool.release(FakeContainer("newer"), "img", False)
    pool.release(FakeContainer("newest"), "img", False)

    assert oldest.removed is True
    assert pool.stats()["total"] == 2


def test_reaper_destroys_idle_containers_only():
    pool = AssignmentService(max_pool_size=4, idle_timeout=0)
    stale = FakeContainer("stale")
    pool.release(stale, "img", False)
    pool.reap()

    assert stale.removed is True
    assert pool.stats()["total"] == 0


def test_shutdown_destroys_everything():
    pool = AssignmentService(max_pool_size=4)
    containers = [FakeContainer(f"c{i}") for i in range(3)]
    for c in containers:
        pool.release(c, "img", False)
    pool.shutdown()

    assert all(c.removed for c in containers)
    assert pool.stats()["total"] == 0
