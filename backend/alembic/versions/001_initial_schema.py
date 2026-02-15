"""Initial schema - functions and invocations tables.

Revision ID: 001
Revises: None
Create Date: 2026-02-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy import inspect

revision: str = "001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Check if tables already exist (handles existing databases that
    # were created with create_all before we added Alembic).
    conn = op.get_bind()
    inspector = inspect(conn)
    existing_tables = inspector.get_table_names()

    if "functions" not in existing_tables:
        op.create_table(
            "functions",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("name", sa.String(), nullable=False),
            sa.Column("description", sa.String(), nullable=False),
            sa.Column("code", sa.Text(), nullable=False),
            sa.Column("runtime", sa.String(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.Column("updated_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(op.f("ix_functions_name"), "functions", ["name"])

    if "invocations" not in existing_tables:
        op.create_table(
            "invocations",
            sa.Column("id", sa.String(), nullable=False),
            sa.Column("function_id", sa.String(), nullable=False),
            sa.Column("input", sa.Text(), nullable=False),
            sa.Column("output", sa.Text(), nullable=False),
            sa.Column("status", sa.String(), nullable=False),
            sa.Column("duration_ms", sa.Integer(), nullable=False),
            sa.Column("created_at", sa.DateTime(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.ForeignKeyConstraint(["function_id"], ["functions.id"]),
        )


def downgrade() -> None:
    op.drop_table("invocations")
    op.drop_table("functions")
