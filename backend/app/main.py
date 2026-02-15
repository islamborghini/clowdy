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

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import FRONTEND_URL
from app.database import engine
from app.models import Base
from app.routers import functions, invoke


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


@app.get("/api/health")
async def health():
    """Simple health check endpoint. Returns {"status": "ok"} if the server is running."""
    return {"status": "ok"}
