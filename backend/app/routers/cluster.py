"""
Cluster observability router.

Exposes the fleet the scheduler is working with: which workers are alive,
how loaded they are, how many warm containers they hold, and what share of
invocations each one has served. This is what the Cluster page renders, and
it is the endpoint to hit when a load test looks unbalanced.

Public on purpose -- it reports no user data, only node-level counters, and
being able to curl it without a token is the difference between debugging a
placement problem in ten seconds and ten minutes.
"""

from fastapi import APIRouter, Depends, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models import Invocation
from app.services.scheduler import BALANCE_FACTOR, VNODES

router = APIRouter(prefix="/api/cluster", tags=["cluster"])


@router.get("")
async def cluster_state(request: Request, db: AsyncSession = Depends(get_db)):
    """
    Current fleet state plus the placement policy in effect.

    `mode` is "distributed" when workers have registered and "single-node"
    when the control plane is executing locally, which is the honest answer
    for a laptop running `uvicorn` with no Redis.
    """
    registry = request.app.state.registry
    workers = await registry.list_workers()

    # Per-worker invocation counts from the durable log, so the numbers survive
    # a worker restart (the in-memory heartbeat counters do not).
    rows = await db.execute(
        select(Invocation.worker_id, func.count())
        .group_by(Invocation.worker_id)
    )
    logged = {worker_id: count for worker_id, count in rows.all()}

    cold_rows = await db.execute(
        select(func.count()).select_from(Invocation).where(Invocation.cold_start.is_(True))
    )
    cold_total = cold_rows.scalar() or 0
    total_rows = await db.execute(select(func.count()).select_from(Invocation))
    total = total_rows.scalar() or 0

    return {
        "mode": "distributed" if workers else "single-node",
        "redis_enabled": registry.enabled,
        "policy": {
            "algorithm": "consistent-hash-bounded-load",
            "affinity_key": "image|network",
            "virtual_nodes": VNODES,
            "balance_factor": BALANCE_FACTOR,
        },
        "totals": {
            "invocations": total,
            "cold_starts": cold_total,
            "warm_rate": round((1 - cold_total / total) * 100) if total else 0,
        },
        "workers": [
            {
                "id": w.id,
                "url": w.url,
                "capacity": w.capacity,
                "inflight": w.inflight,
                "load": round(w.load * 100),
                "warm_containers": w.warm_containers,
                "invocations_total": logged.get(w.id, 0),
                "invocations_since_start": w.invocations,
                "cold_starts_since_start": w.cold_starts,
                "uptime_seconds": round(w.uptime_seconds),
            }
            for w in workers
        ],
    }
