"""
Application configuration.

Settings are loaded from a .env.local file (if it exists) and environment
variables. Environment variables take precedence over the file.

For local development, create backend/.env.local with your API keys.
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env.local from the backend directory (one level up from app/)
_backend_dir = Path(__file__).resolve().parent.parent
load_dotenv(_backend_dir / ".env.local")

# SQLite database URL using the async aiosqlite driver.
# Format: "sqlite+aiosqlite:///./filename.db"
#   - "sqlite" = database type
#   - "+aiosqlite" = async Python driver (lets us use await with DB queries)
#   - "///./clowdy.db" = relative file path (three slashes = relative, four = absolute)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./clowdy.db")

# The frontend URL, used to configure CORS (Cross-Origin Resource Sharing).
# CORS is a browser security feature that blocks requests from one origin
# (e.g. localhost:5173) to another (e.g. localhost:8000) unless explicitly allowed.
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")

# Groq API key for the AI agent.
# Get a free key at https://console.groq.com/keys
# Set it in your environment: export GROQ_API_KEY="gsk_..."
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")

# Clerk authentication settings.
# Get these from your Clerk dashboard at https://dashboard.clerk.com
# CLERK_JWKS_URL is your instance's JWKS endpoint for verifying JWTs.
# Format: https://<your-instance>.clerk.accounts.dev/.well-known/jwks.json
CLERK_JWKS_URL = os.getenv("CLERK_JWKS_URL", "")

# Neon API key for managed PostgreSQL databases.
# Get a free key at https://console.neon.tech/account/api-keys
NEON_API_KEY = os.getenv("NEON_API_KEY", "")


# ---------------------------------------------------------------------------
# Cluster configuration
#
# Clowdy runs as two node roles:
#   control-plane -- the API, gateway, auth, and scheduler (this FastAPI app)
#   worker        -- a data-plane node that owns a Docker daemon and a warm pool
#
# Workers register themselves in Redis with a TTL. The control plane reads that
# registry to load-balance invocations. With no Redis and no workers registered,
# the control plane falls back to executing locally, so single-machine
# development still works with zero extra infrastructure.
# ---------------------------------------------------------------------------

# Redis holds the worker registry, per-worker in-flight counters, and rate
# limits. Empty means "no cluster" -- run everything in this process.
REDIS_URL = os.getenv("REDIS_URL", "")

# Identity this node advertises in the registry. Defaults to the hostname,
# which is the container ID under Docker Compose and the task ID on ECS.
WORKER_ID = os.getenv("WORKER_ID", "") or os.uname().nodename

# The address other nodes use to reach this worker's /run endpoint. Left empty,
# the worker advertises its own routable IP on WORKER_PORT.
WORKER_URL = os.getenv("WORKER_URL", "")

# Port the worker serves on. Must match what uvicorn is bound to, or the
# control plane will dispatch to an address nothing is listening on.
WORKER_PORT = int(os.getenv("WORKER_PORT", "9000"))

# Maximum concurrent invocations this worker accepts. The scheduler refuses to
# place work on a worker already at capacity, which is what turns a queue into
# backpressure instead of an unbounded pile of Docker execs.
WORKER_CONCURRENCY = int(os.getenv("WORKER_CONCURRENCY", "8"))

# Seconds a worker's registry entry survives without a heartbeat. A crashed
# worker disappears from the ring after this long with no further action.
WORKER_TTL_SECONDS = int(os.getenv("WORKER_TTL_SECONDS", "15"))

# Run Alembic migrations on startup. Set false for control-plane replicas so a
# single one-shot migrate job owns the schema instead of N replicas racing.
RUN_MIGRATIONS = os.getenv("RUN_MIGRATIONS", "true").lower() != "false"

# Log SQL statements. Noisy; off by default outside local development.
SQL_ECHO = os.getenv("SQL_ECHO", "false").lower() == "true"

# Read-only demo mode. Blocks every state-changing request except invoking a
# function and calling a gateway route, so a public deployment can show the
# platform without handing strangers code execution on the host.
DEMO_MODE = os.getenv("DEMO_MODE", "false").lower() == "true"

# Identity every visitor to the demo shares. Reads are attributed to it so a
# public visitor sees the seeded content instead of a wall of 401s; writes are
# blocked by the demo middleware regardless of who is asking.
DEMO_USER_ID = "demo"
