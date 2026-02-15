import os

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///./clowdy.db")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
