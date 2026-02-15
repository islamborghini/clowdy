import uuid
from datetime import datetime, timezone

from sqlalchemy import ForeignKey, Text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


def generate_id() -> str:
    return uuid.uuid4().hex[:12]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Base(DeclarativeBase):
    pass


class Function(Base):
    __tablename__ = "functions"

    id: Mapped[str] = mapped_column(primary_key=True, default=generate_id)
    name: Mapped[str] = mapped_column(index=True)
    description: Mapped[str] = mapped_column(default="")
    code: Mapped[str] = mapped_column(Text)
    runtime: Mapped[str] = mapped_column(default="python")
    status: Mapped[str] = mapped_column(default="active")  # active, error
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    invocations: Mapped[list["Invocation"]] = relationship(back_populates="function")


class Invocation(Base):
    __tablename__ = "invocations"

    id: Mapped[str] = mapped_column(primary_key=True, default=generate_id)
    function_id: Mapped[str] = mapped_column(ForeignKey("functions.id"))
    input: Mapped[str] = mapped_column(Text, default="{}")
    output: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(default="pending")  # pending, success, error, timeout
    duration_ms: Mapped[int] = mapped_column(default=0)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    function: Mapped["Function"] = relationship(back_populates="invocations")
