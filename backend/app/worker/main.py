"""
Worker node -- the data plane.

AWS Lambda equivalent: a worker host running Firecracker microVMs.

One of these runs per machine that has a Docker daemon. It owns a warm
container pool and executes code; it knows nothing about projects, users,
routes, or the database. Its entire contract with the control plane is:

    POST /run     run this code, here is the result
    GET  /health  here is my load

Admission control lives here, not only in the scheduler. The control plane's
view of a worker's load is up to one heartbeat stale, so a worker must be able
to refuse work it cannot take. Refusing with 429 is cheap and the dispatcher
fails over to another node; accepting past capacity is how a single slow
function takes a host down.

Run it with:
    ./venv/bin/uvicorn app.worker.main:app --port 9000
"""

import asyncio
import logging
import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.config import (
    REDIS_URL,
    WORKER_CONCURRENCY,
    WORKER_ID,
    WORKER_PORT,
    WORKER_TTL_SECONDS,
    WORKER_URL,
)
from app.services.assignment_service import AssignmentService
from app.services.invoke_service import InvokeService
from app.services.placement_service import PlacementService
from app.services.registry import WorkerRegistry, new_worker_info

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Heartbeat well inside the TTL so a single dropped beat does not evict a
# healthy worker from the ring.
HEARTBEAT_INTERVAL = max(1, WORKER_TTL_SECONDS // 3)


class RunRequest(BaseModel):
    """One invocation as sent by the control plane's dispatcher."""

    code: str
    input_data: dict
    env_vars: dict[str, str] | None = None
    function_name: str = "unknown"
    image_name: str | None = None
    network_enabled: bool = False


def _routable_address() -> str:
    """
    The address other containers can reach this worker on.

    Opening a UDP socket toward an arbitrary external address and reading back
    the local end reveals which interface the kernel would route out of. No
    packet is sent, and it works with no DNS and no network. Advertising an IP
    rather than a hostname means the registry entry stays valid regardless of
    how the orchestrator names replicas.
    """
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("10.255.255.255", 1))
        return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        sock.close()


async def _heartbeat_loop(app: FastAPI) -> None:
    """Publish liveness and load into the registry until cancelled."""
    while True:
        try:
            info = app.state.info
            info.warm_containers = app.state.assignment.stats()["total"]
            info.invocations = app.state.invocations
            info.cold_starts = app.state.cold_starts
            await app.state.registry.heartbeat(info)
        except Exception as exc:
            logger.warning("Heartbeat failed: %s", exc)
        await asyncio.sleep(HEARTBEAT_INTERVAL)


@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.placement = PlacementService()
    app.state.assignment = AssignmentService(max_pool_size=10, idle_timeout=300)
    app.state.invoke_service = InvokeService(app.state.assignment, app.state.placement)
    app.state.inflight = 0
    app.state.invocations = 0
    app.state.cold_starts = 0

    url = WORKER_URL or f"http://{_routable_address()}:{WORKER_PORT}"
    app.state.info = new_worker_info(WORKER_ID, url, WORKER_CONCURRENCY)
    app.state.registry = WorkerRegistry(REDIS_URL, WORKER_TTL_SECONDS)
    await app.state.registry.connect()

    tasks = [
        asyncio.create_task(app.state.assignment.run_reaper()),
        asyncio.create_task(_heartbeat_loop(app)),
    ]
    logger.info(
        "Worker %s online at %s (concurrency=%d)", WORKER_ID, url, WORKER_CONCURRENCY
    )

    yield

    # Drain: leave the ring first so no new work arrives, then tear down.
    await app.state.registry.deregister(WORKER_ID)
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    app.state.assignment.shutdown()
    await app.state.registry.aclose()


app = FastAPI(title="Clowdy Worker", version="1.0.0", lifespan=lifespan)


@app.get("/health")
async def health():
    """Liveness plus the load numbers the cluster view renders."""
    return {
        "status": "ok",
        "worker_id": WORKER_ID,
        "capacity": WORKER_CONCURRENCY,
        "inflight": app.state.inflight,
        "invocations": app.state.invocations,
        "cold_starts": app.state.cold_starts,
        "pool": app.state.assignment.stats(),
    }


@app.post("/run")
async def run(req: RunRequest):
    """
    Execute one function. Refuses immediately when already at capacity.

    Refusing rather than queueing is the point: a worker that queues looks
    healthy to the scheduler while its latency climbs, and the whole fleet
    piles onto it.
    """
    if app.state.inflight >= WORKER_CONCURRENCY:
        return JSONResponse(
            status_code=429,
            content={"detail": f"Worker {WORKER_ID} at capacity"},
        )

    # Safe without a lock: the check above and this increment are not separated
    # by an await, so no other task can interleave between them.
    app.state.inflight += 1
    app.state.invocations += 1
    try:
        result = await app.state.invoke_service.invoke(
            code=req.code,
            input_data=req.input_data,
            env_vars=req.env_vars,
            function_name=req.function_name,
            image_name=req.image_name,
            network_enabled=req.network_enabled,
        )
    finally:
        app.state.inflight -= 1

    if result.get("cold_start"):
        app.state.cold_starts += 1
    result["worker_id"] = WORKER_ID
    return result
