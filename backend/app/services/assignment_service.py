"""
Assignment Service -- tracks and assigns warm containers to invocations.

AWS Lambda equivalent: Assignment Service.

Maintains a pool of warm (already-running) containers keyed by
(image_name, network_enabled). When an invocation comes in, it checks
the pool first (warm path). If no warm container is available, the
caller falls back to the Placement Service (cold path).

A background reaper periodically destroys containers that have been
idle for too long, freeing Docker resources.
"""

import asyncio
import logging
import threading
import time
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class PoolEntry:
    """A warm container sitting in the pool waiting for work."""
    container: object
    idle_since: float = field(default_factory=time.time)


class AssignmentService:
    """
    Warm container pool with LRU eviction and idle timeout.

    Pool key: (image_name, network_enabled)
    This means one warm container can serve ANY function using the same
    image + network setting. Code and env vars are injected at exec time.
    """

    def __init__(
        self,
        max_pool_size: int = 10,
        idle_timeout: int = 300,
        reap_interval: int = 30,
    ):
        self.max_pool_size = max_pool_size
        self.idle_timeout = idle_timeout  # seconds before idle container is reaped
        self.reap_interval = reap_interval  # seconds between reaper runs
        self._pool: dict[tuple, list[PoolEntry]] = {}
        self._lock = threading.Lock()

    def acquire(self, image: str, network_enabled: bool):
        """
        Take a warm container from the pool.

        Returns a Docker container if one is available for the given
        image + network setting, or None if the pool has no match (cold start).
        """
        key = (image, network_enabled)
        with self._lock:
            entries = self._pool.get(key, [])
            if entries:
                entry = entries.pop()
                logger.info(
                    "Warm hit for %s (pool has %d remaining for this key)",
                    key, len(entries),
                )
                return entry.container
        return None

    def release(self, container, image: str, network_enabled: bool):
        """
        Return a container to the pool after invocation.

        If the pool is full, the least-recently-used container across
        all keys is evicted and destroyed.
        """
        key = (image, network_enabled)
        with self._lock:
            if self._total_count() >= self.max_pool_size:
                self._evict_lru()
            self._pool.setdefault(key, []).append(
                PoolEntry(container=container, idle_since=time.time())
            )
            logger.info(
                "Released container back to pool for %s (total pool: %d)",
                key, self._total_count(),
            )

    def _total_count(self) -> int:
        """Total number of containers across all pool keys."""
        return sum(len(entries) for entries in self._pool.values())

    def _evict_lru(self):
        """
        Remove the least-recently-used container from the pool.
        Must be called while holding self._lock.
        """
        oldest_key = None
        oldest_time = float("inf")
        oldest_idx = -1

        for key, entries in self._pool.items():
            for idx, entry in enumerate(entries):
                if entry.idle_since < oldest_time:
                    oldest_time = entry.idle_since
                    oldest_key = key
                    oldest_idx = idx

        if oldest_key is not None and oldest_idx >= 0:
            entry = self._pool[oldest_key].pop(oldest_idx)
            if not self._pool[oldest_key]:
                del self._pool[oldest_key]
            try:
                entry.container.remove(force=True)
            except Exception:
                pass
            logger.info("Evicted LRU container for %s", oldest_key)

    def reap(self):
        """
        Destroy containers that have been idle longer than idle_timeout.
        Called periodically by the background reaper task.
        """
        now = time.time()
        to_remove = []

        with self._lock:
            for key, entries in self._pool.items():
                still_alive = []
                for entry in entries:
                    if now - entry.idle_since > self.idle_timeout:
                        to_remove.append(entry.container)
                    else:
                        still_alive.append(entry)
                self._pool[key] = still_alive

            # Clean up empty keys
            self._pool = {k: v for k, v in self._pool.items() if v}

        # Destroy outside the lock to avoid blocking
        for container in to_remove:
            try:
                container.remove(force=True)
            except Exception:
                pass

        if to_remove:
            logger.info("Reaped %d idle containers", len(to_remove))

    async def run_reaper(self):
        """
        Background task that periodically reaps idle containers.
        Run this as an asyncio task in the FastAPI lifespan.
        """
        while True:
            await asyncio.sleep(self.reap_interval)
            try:
                self.reap()
            except Exception as exc:
                logger.error("Reaper error: %s", exc)

    def shutdown(self):
        """
        Destroy all pooled containers. Called on application shutdown.
        """
        with self._lock:
            count = 0
            for entries in self._pool.values():
                for entry in entries:
                    try:
                        entry.container.remove(force=True)
                        count += 1
                    except Exception:
                        pass
            self._pool.clear()
        logger.info("Shutdown: destroyed %d pooled containers", count)

    def stats(self) -> dict:
        """Return pool statistics for monitoring."""
        with self._lock:
            per_key = {
                f"{k[0]}|net={k[1]}": len(v) for k, v in self._pool.items()
            }
            return {
                "total": self._total_count(),
                "max": self.max_pool_size,
                "by_key": per_key,
            }
