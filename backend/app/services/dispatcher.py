"""
Dispatcher -- the control plane's entry point for running a function.

AWS Lambda equivalent: the Frontend Invoke Service talking to the worker fleet.

This is a drop-in replacement for InvokeService: same `invoke()` signature, so
the invoke, gateway, and chat routers never learn whether the code ran in this
process or on another machine. It:

  1. reads the live fleet from the registry
  2. asks the scheduler for a placement order
  3. POSTs the invocation to the chosen worker
  4. fails over down the order on refusal, timeout, or connection error

With no workers registered it delegates to a local InvokeService, so the same
binary is a complete single-node platform on a laptop and a control plane in
a cluster. That fallback is the reason there is no separate "dev mode".
"""

import logging

import httpx

from app.services.invoke_service import InvokeService
from app.services.placement_service import DEFAULT_IMAGE
from app.services.registry import WorkerRegistry
from app.services.scheduler import plan, pool_key

logger = logging.getLogger(__name__)

# Workers to try before giving up. Every attempt costs a caller-visible retry,
# so this is deliberately small -- a fleet where three consecutive nodes refuse
# is a fleet that should be shedding load, not retrying harder.
MAX_ATTEMPTS = 3

# Must exceed the worker's own function timeout (30s) so that a function
# hitting its limit returns a real error instead of a dispatch timeout.
DISPATCH_TIMEOUT_SECONDS = 45.0


class Dispatcher:
    """Routes invocations across the worker fleet, or locally if there is none."""

    def __init__(self, registry: WorkerRegistry, local: InvokeService):
        self.registry = registry
        self.local = local
        self._client = httpx.AsyncClient(timeout=DISPATCH_TIMEOUT_SECONDS)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def invoke(
        self,
        code: str,
        input_data: dict,
        env_vars: dict[str, str] | None = None,
        function_name: str = "unknown",
        image_name: str | None = None,
        network_enabled: bool = False,
    ) -> dict:
        payload = {
            "code": code,
            "input_data": input_data,
            "env_vars": env_vars,
            "function_name": function_name,
            "image_name": image_name,
            "network_enabled": network_enabled,
        }

        workers = await self.registry.list_workers()
        if not workers:
            result = await self.local.invoke(**payload)
            result["worker_id"] = "local"
            return result

        key = pool_key(image_name or DEFAULT_IMAGE, network_enabled)
        candidates = plan(workers, key)
        if not candidates:
            return {
                "success": False,
                "output": (
                    f"Fleet at capacity: all {len(workers)} workers are running "
                    "their maximum concurrent invocations. Retry shortly."
                ),
                "duration_ms": 0,
                "cold_start": False,
                "worker_id": None,
                "throttled": True,
            }

        errors = []
        # Distinguishes "the fleet is full" from "the fleet is broken". Both
        # exhaust the candidates, but the first is backpressure the caller
        # should retry (503 + Retry-After) and the second is a real failure.
        # Getting this wrong logs every throttle as a function error.
        capacity_only = True

        for worker in candidates[:MAX_ATTEMPTS]:
            await self.registry.acquire_slot(worker.id)
            try:
                response = await self._client.post(f"{worker.url}/run", json=payload)
                if response.status_code == 429:
                    # Worker's own admission control refused. Its heartbeat was
                    # stale; try the next node rather than waiting on this one.
                    errors.append(f"{worker.id}: at capacity")
                    continue
                response.raise_for_status()
                result = response.json()
                result["worker_id"] = worker.id
                return result
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("Worker %s failed (%s), failing over", worker.id, exc)
                errors.append(f"{worker.id}: {type(exc).__name__}")
                capacity_only = False
            finally:
                await self.registry.release_slot(worker.id)

        if capacity_only:
            return {
                "success": False,
                "output": (
                    "Fleet at capacity: every worker tried was already running its "
                    "maximum concurrent invocations. Retry shortly."
                ),
                "duration_ms": 0,
                "cold_start": False,
                "worker_id": None,
                "throttled": True,
            }

        return {
            "success": False,
            "output": "No worker could run this invocation. " + "; ".join(errors),
            "duration_ms": 0,
            "cold_start": False,
            "worker_id": None,
        }
