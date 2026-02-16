"""
FastAPI application entry point.

This is the main file that creates and configures the FastAPI app.
Run it with: ./venv/bin/uvicorn app.main:app --reload

Key concepts:
- Lifespan: runs setup code on startup and cleanup code on shutdown
- CORS middleware: allows the React frontend to make requests to this API
- Routers: modular groups of related endpoints (imported from routers/)
"""

import os
from contextlib import asynccontextmanager

from alembic import command
from alembic.config import Config
from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import get_current_user
from app.config import FRONTEND_URL
from app.database import engine, get_db
from app.models import Function, Invocation
from app.routers import chat, env_vars, functions, gateway, invoke, projects, requirements, routes


def _run_migrations() -> None:
    """Run Alembic migrations on startup.

    Finds the alembic.ini relative to this file (in the backend/ directory)
    and upgrades the database to the latest migration.
    """
    backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    alembic_cfg = Config(os.path.join(backend_dir, "alembic.ini"))
    alembic_cfg.set_main_option("script_location", os.path.join(backend_dir, "alembic"))
    command.upgrade(alembic_cfg, "head")


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Code before "yield" runs on startup - we run Alembic migrations to
    ensure the database schema is up to date. Alembic handles both creating
    new tables and altering existing ones.

    Code after "yield" runs on shutdown - we clean up the database connection pool.
    """
    _run_migrations()
    yield
    await engine.dispose()


app = FastAPI(title="Clowdy", version="0.1.0", lifespan=lifespan)

# CORS (Cross-Origin Resource Sharing) middleware.
# Browsers block requests from one origin (localhost:5173) to another
# (localhost:8000) by default. This middleware tells the browser
# "it's OK, the frontend at FRONTEND_URL is allowed to call this API."
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],  # Allow all HTTP methods (GET, POST, PUT, DELETE)
    allow_headers=["*"],  # Allow all headers (including Content-Type, Authorization)
)

# Register routers - each adds a group of related endpoints
app.include_router(projects.router)
app.include_router(env_vars.router)
app.include_router(routes.router)
app.include_router(requirements.router)
app.include_router(functions.router)
app.include_router(invoke.router)
app.include_router(chat.router)
app.include_router(gateway.router)


@app.get("/api/health")
async def health():
    """Simple health check endpoint. Returns {"status": "ok"} if the server is running."""
    return {"status": "ok"}


@app.get("/api/stats")
async def stats(
    user_id: str = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Dashboard statistics endpoint.

    Returns aggregate numbers for the dashboard: total functions,
    total invocations, success count, and average duration.
    Filtered to the authenticated user's functions only.
    """
    # Count total functions for this user
    fn_result = await db.execute(
        select(func.count()).select_from(Function).where(Function.user_id == user_id)
    )
    total_functions = fn_result.scalar() or 0

    # Count total invocations and successes, average duration (for this user's functions)
    inv_result = await db.execute(
        select(
            func.count(),
            func.count().filter(Invocation.status == "success"),
            func.avg(Invocation.duration_ms),
        )
        .select_from(Invocation)
        .join(Function)
        .where(Function.user_id == user_id)
    )
    row = inv_result.one()
    total_invocations = row[0] or 0
    successful = row[1] or 0
    avg_duration = round(row[2] or 0)

    success_rate = round((successful / total_invocations) * 100) if total_invocations > 0 else 0

    return {
        "total_functions": total_functions,
        "total_invocations": total_invocations,
        "success_rate": success_rate,
        "avg_duration_ms": avg_duration,
    }
