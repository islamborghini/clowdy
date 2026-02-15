"""
Database connection setup.

Creates the SQLAlchemy async engine and session factory. The engine manages
the connection pool to SQLite, and the session factory creates individual
database sessions for each request.

Key concepts:
- Engine: the connection pool manager (one per app, created once at startup)
- Session: a single "conversation" with the database (one per API request)
- async_sessionmaker: a factory that creates new sessions on demand
"""

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config import DATABASE_URL

# Create the async database engine.
# echo=True prints all SQL queries to the console (helpful for debugging).
engine = create_async_engine(DATABASE_URL, echo=True)

# Session factory. Each call to async_session() creates a new database session.
# expire_on_commit=False means objects stay usable after commit (otherwise
# accessing attributes would trigger a lazy load, which doesn't work with async).
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():
    """
    FastAPI dependency that provides a database session to route handlers.

    Usage in a route:
        @router.get("/items")
        async def get_items(db: AsyncSession = Depends(get_db)):
            ...

    The "yield" makes this a generator - FastAPI will:
      1. Call get_db() to create a session
      2. Pass it to your route handler
      3. After the handler returns, close the session automatically

    This pattern ensures sessions are always properly cleaned up.
    """
    async with async_session() as session:
        yield session
