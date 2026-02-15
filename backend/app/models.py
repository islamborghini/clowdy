"""
SQLAlchemy database models.

These classes define the structure of our database tables. SQLAlchemy's ORM
(Object-Relational Mapper) lets us work with database rows as Python objects
instead of writing raw SQL.

For example, instead of:
    INSERT INTO functions (name, code) VALUES ('hello', 'print("hi")')
We write:
    fn = Function(name="hello", code='print("hi")')
    db.add(fn)

Models use SQLAlchemy 2.x modern syntax:
    - Mapped[type] declares the column's Python type
    - mapped_column() configures the database column
"""

import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def generate_id() -> str:
    """Generate a short random ID (12 hex characters) for use as primary keys."""
    return uuid.uuid4().hex[:12]


def utcnow() -> datetime:
    """Return the current UTC time. Used as default value for timestamp columns."""
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    """
    Base class for all models. All our model classes inherit from this.
    SQLAlchemy uses this to track all models and generate the database schema.
    """

    pass


class Function(Base):
    """
    A serverless function created by a user.

    This maps to the "functions" table in SQLite. Each row represents one
    deployed function with its source code and metadata.

    Columns:
        id          - Unique identifier (auto-generated, e.g. "a1b2c3d4e5f6")
        name        - Human-readable name (e.g. "celsius_converter")
        description - Optional description of what the function does
        code        - The actual source code (stored as text)
        runtime     - Language runtime to use (currently only "python")
        status      - "active" or "error"
        created_at  - When the function was first created
        updated_at  - When the function was last modified
    """

    __tablename__ = "functions"

    id: Mapped[str] = mapped_column(primary_key=True, default=generate_id)
    name: Mapped[str] = mapped_column(index=True)
    description: Mapped[str] = mapped_column(default="")
    code: Mapped[str] = mapped_column(Text)
    runtime: Mapped[str] = mapped_column(default="python")
    status: Mapped[str] = mapped_column(default="active")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    # onupdate=utcnow automatically updates this timestamp whenever the row is modified
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    # Relationship: one function has many invocations.
    # back_populates creates a two-way link (function.invocations <-> invocation.function).
    invocations: Mapped[list["Invocation"]] = relationship(back_populates="function")


class Invocation(Base):
    """
    A record of a single function execution (invocation).

    Every time someone calls a function via the invoke endpoint, we create
    an Invocation row to log the input, output, status, and timing.

    Columns:
        id          - Unique identifier
        function_id - Which function was invoked (foreign key to functions.id)
        input       - JSON string of the input data sent to the function
        output      - The function's return value (or error message)
        status      - "pending", "success", "error", or "timeout"
        duration_ms - How long the execution took in milliseconds
        created_at  - When the invocation happened
    """

    __tablename__ = "invocations"

    id: Mapped[str] = mapped_column(primary_key=True, default=generate_id)
    # ForeignKey links this column to functions.id - the database enforces
    # that every invocation must reference an existing function.
    function_id: Mapped[str] = mapped_column(ForeignKey("functions.id"))
    input: Mapped[str] = mapped_column(Text, default="{}")
    output: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(default="pending")
    duration_ms: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    # Reverse relationship: access the parent function from an invocation object.
    function: Mapped["Function"] = relationship(back_populates="invocations")
