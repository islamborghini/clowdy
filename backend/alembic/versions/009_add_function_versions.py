"""Add function_versions table and migrate code from functions.

Creates the function_versions table with composite PK (function_id, version).
Migrates existing function code into version 1 rows, adds active_version
column to functions, then drops the code column.

Revision ID: 009
Revises: 008
Create Date: 2026-02-21
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "009"
down_revision: Union[str, None] = "008"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create the function_versions table
    op.create_table(
        "function_versions",
        sa.Column("function_id", sa.String(), sa.ForeignKey("functions.id"), primary_key=True),
        sa.Column("version", sa.Integer(), primary_key=True),
        sa.Column("code", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
    )

    # 2. Add active_version column to functions (default 1)
    op.add_column(
        "functions",
        sa.Column("active_version", sa.Integer(), nullable=False, server_default="1"),
    )

    # 3. Migrate existing code into function_versions as version 1
    op.execute(
        "INSERT INTO function_versions (function_id, version, code, created_at, updated_at) "
        "SELECT id, 1, code, created_at, updated_at FROM functions"
    )

    # 4. Drop the code column from functions
    op.drop_column("functions", "code")


def downgrade() -> None:
    # 1. Re-add code column to functions
    op.add_column(
        "functions",
        sa.Column("code", sa.Text(), nullable=False, server_default=""),
    )

    # 2. Restore code from the active version
    op.execute(
        "UPDATE functions SET code = ("
        "  SELECT fv.code FROM function_versions fv "
        "  WHERE fv.function_id = functions.id AND fv.version = functions.active_version"
        ")"
    )

    # 3. Drop active_version column
    op.drop_column("functions", "active_version")

    # 4. Drop function_versions table
    op.drop_table("function_versions")
