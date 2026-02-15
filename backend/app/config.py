"""
Application configuration.

Settings are loaded from environment variables with sensible defaults
for local development. In production, you'd set these via .env file or
your hosting platform's environment variable settings.
"""

import os

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
