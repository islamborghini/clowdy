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


class Project(Base):
    """
    A project groups related functions under a single deployable unit.

    Projects are the top-level organizational entity. In later phases they
    will also hold routes, environment variables, and database connections.
    """

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(primary_key=True, default=generate_id)
    user_id: Mapped[str] = mapped_column(index=True)
    name: Mapped[str] = mapped_column(index=True)
    slug: Mapped[str] = mapped_column(unique=True)
    description: Mapped[str] = mapped_column(default="")
    status: Mapped[str] = mapped_column(default="active")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    functions: Mapped[list["Function"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class Function(Base):
    """
    A serverless function created by a user.

    This maps to the "functions" table in SQLite. Each row represents one
    deployed function with its source code and metadata.
    """

    __tablename__ = "functions"

    id: Mapped[str] = mapped_column(primary_key=True, default=generate_id)
    user_id: Mapped[str | None] = mapped_column(default=None, index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id"), default=None, index=True
    )
    name: Mapped[str] = mapped_column(index=True)
    description: Mapped[str] = mapped_column(default="")
    code: Mapped[str] = mapped_column(Text)
    runtime: Mapped[str] = mapped_column(default="python")
    status: Mapped[str] = mapped_column(default="active")
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    project: Mapped["Project | None"] = relationship(back_populates="functions")
    invocations: Mapped[list["Invocation"]] = relationship(
        back_populates="function", cascade="all, delete-orphan"
    )


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
