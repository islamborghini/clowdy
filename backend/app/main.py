"""
FastAPI application entry point.

This is the main file that creates and configures the FastAPI app.
Run it with: ./venv/bin/uvicorn app.main:app --reload

Key concepts:
- Lifespan: runs setup code on startup and cleanup code on shutdown
- CORS middleware: allows the React frontend to make requests to this API
- Routers: modular groups of related endpoints (imported from routers/)
"""

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import FRONTEND_URL
from app.database import engine, get_db
from app.models import Base, Function, Invocation
from app.routers import chat, functions, invoke


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Application lifespan handler.

    Code before "yield" runs on startup - we use it to create database tables
    if they don't exist yet (create_all is safe to call multiple times).

    Code after "yield" runs on shutdown - we clean up the database connection pool.
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
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
app.include_router(functions.router)
app.include_router(invoke.router)
app.include_router(chat.router)


@app.get("/api/health")
async def health():
    """Simple health check endpoint. Returns {"status": "ok"} if the server is running."""
    return {"status": "ok"}


@app.get("/api/stats")
async def stats(db: AsyncSession = Depends(get_db)):
    """
    Dashboard statistics endpoint.

    Returns aggregate numbers for the dashboard: total functions,
    total invocations, success count, and average duration.
    All computed with SQL COUNT/AVG so it's fast even with lots of data.
    """
    # Count total functions
    fn_result = await db.execute(select(func.count()).select_from(Function))
    total_functions = fn_result.scalar() or 0

    # Count total invocations and successes, average duration
    inv_result = await db.execute(
        select(
            func.count(),
            func.count().filter(Invocation.status == "success"),
            func.avg(Invocation.duration_ms),
        ).select_from(Invocation)
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
