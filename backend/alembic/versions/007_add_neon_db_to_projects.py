"""Add neon_project_id and database_url columns to projects table.

These columns support per-project managed PostgreSQL databases via Neon.
neon_project_id stores the Neon project ID (needed for deletion),
database_url stores the full connection string for runtime injection.

Revision ID: 007
Revises: 006
Create Date: 2026-02-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "007"
down_revision: Union[str, None] = "006"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("neon_project_id", sa.String(), nullable=False, server_default=""),
    )
    op.add_column(
        "projects",
        sa.Column("database_url", sa.Text(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("projects", "database_url")
    op.drop_column("projects", "neon_project_id")
