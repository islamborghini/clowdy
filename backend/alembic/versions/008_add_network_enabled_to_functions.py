"""Add network_enabled column to functions table.

Allows per-function control over outbound network access in Docker containers.
Defaults to False (network disabled) for security.

Revision ID: 008
Revises: 007
Create Date: 2026-02-20
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "008"
down_revision: Union[str, None] = "007"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "functions",
        sa.Column("network_enabled", sa.Boolean(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("functions", "network_enabled")
