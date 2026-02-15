"""Add user_id column to functions table.

Revision ID: 002
Revises: 001
Create Date: 2026-02-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "002"
down_revision: Union[str, None] = "001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("functions", sa.Column("user_id", sa.String(), nullable=True))
    op.create_index(op.f("ix_functions_user_id"), "functions", ["user_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_functions_user_id"), table_name="functions")
    op.drop_column("functions", "user_id")
