"""
Invoke Service -- orchestrates the full function invocation flow.

AWS Lambda equivalent: Frontend Invoke Service.

This is the single entry point for running user code. It coordinates:
1. Assignment Service (warm path) -- check for an existing container
2. Placement Service (cold path) -- create a new one if needed
3. Worker Service -- execute the code inside the container
4. Return container to pool (or destroy if broken)

Routers (invoke, gateway, chat) all call this service instead of
talking to Docker directly.
"""

import asyncio
import logging
import time

from docker.errors import ImageNotFound

from app.services.assignment_service import AssignmentService
from app.services.placement_service import DEFAULT_IMAGE, PlacementService
from app.services.worker_service import execute as worker_execute

logger = logging.getLogger(__name__)


class InvokeService:
    """
    Orchestrates function invocation across the service layer.

    All container lifecycle decisions flow through here:
    - Warm container available? Use it (fast path).
    - No warm container? Create one via placement (cold path).
    - Execution failed with container error? Destroy, don't return to pool.
    - Execution succeeded? Return container to pool for reuse.
    """

    def __init__(self, assignment: AssignmentService, placement: PlacementService):
        self.assignment = assignment
        self.placement = placement

    async def invoke(
        self,
        code: str,
        input_data: dict,
        env_vars: dict[str, str] | None = None,
        function_name: str = "unknown",
        image_name: str | None = None,
        network_enabled: bool = False,
    ) -> dict:
        """
        Execute user code and return the result.

        This is an async wrapper that runs the synchronous Docker
        operations in a thread pool.

        Returns:
            dict with keys: success, output, duration_ms, cold_start
        """
        return await asyncio.to_thread(
            self._invoke_sync,
            code, input_data, env_vars, function_name,
            image_name, network_enabled,
        )

    def _invoke_sync(
        self,
        code: str,
        input_data: dict,
        env_vars: dict[str, str] | None,
        function_name: str,
        image_name: str | None,
        network_enabled: bool,
    ) -> dict:
        """
        Synchronous invocation logic. Runs in a thread pool.

        Flow:
        1. Try warm path (Assignment Service)
        2. Fall back to cold path (Placement Service)
        3. Execute code (Worker Service)
        4. Return container to pool or destroy on failure
        """
        image = image_name or DEFAULT_IMAGE
        start_time = time.time()

        try:
            return self._do_invoke(
                image, network_enabled, code, input_data,
                env_vars, function_name, start_time,
            )
        except ConnectionError:
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "output": "Could not connect to Docker. Is Docker running?",
                "duration_ms": duration_ms,
                "cold_start": True,
            }
        except ImageNotFound:
            duration_ms = int((time.time() - start_time) * 1000)
            msg = f"Docker image '{image}' not found. "
            if image_name:
                msg += "The project's custom image may need to be rebuilt."
            else:
                msg += (
                    "Build it with: cd backend/docker/runtimes/python && "
                    "docker build -t clowdy-python-runtime ."
                )
            return {
                "success": False,
                "output": msg,
                "duration_ms": duration_ms,
                "cold_start": True,
            }
        except Exception as exc:
            duration_ms = int((time.time() - start_time) * 1000)
            logger.error("Invoke error: %s", exc)
            return {
                "success": False,
                "output": f"Unexpected error: {exc}",
                "duration_ms": duration_ms,
                "cold_start": True,
            }

    def _do_invoke(
        self,
        image: str,
        network_enabled: bool,
        code: str,
        input_data: dict,
        env_vars: dict[str, str] | None,
        function_name: str,
        start_time: float,
    ) -> dict:
        """
        Core invocation: acquire/create container, execute, release/destroy.
        """
        # 1. Try warm path (Assignment Service)
        container = self.assignment.acquire(image, network_enabled)
        cold_start = container is None

        # 2. Cold path if needed (Placement Service)
        if container is None:
            logger.info("Cold start for image=%s network=%s", image, network_enabled)
            container = self.placement.create(image, network_enabled)

        # 3. Execute code (Worker Service)
        try:
            result = worker_execute(
                container, code, input_data, env_vars, function_name,
            )
        except Exception as exc:
            # Container is broken -- destroy it, don't return to pool
            logger.error("Worker execution failed: %s", exc)
            self.placement.destroy(container)
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "output": f"Execution error: {exc}",
                "duration_ms": duration_ms,
                "cold_start": cold_start,
            }

        # 4. Return container to pool for reuse
        self.assignment.release(container, image, network_enabled)

        duration_ms = int((time.time() - start_time) * 1000)
        result["duration_ms"] = duration_ms
        result["cold_start"] = cold_start
        return result
