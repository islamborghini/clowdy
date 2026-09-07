"""Record where each invocation ran.

Adds worker_id and cold_start to invocations so the cluster view can show how
traffic actually distributed across the fleet and what share of it paid a cold
start. Existing rows predate the fleet and are backfilled as "local".

Revision ID: 010
Revises: 009
Create Date: 2026-09-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "010"
down_revision: Union[str, None] = "009"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "invocations",
        sa.Column("worker_id", sa.String(), nullable=False, server_default="local"),
    )
    op.add_column(
        "invocations",
        sa.Column("cold_start", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.create_index("ix_invocations_worker_id", "invocations", ["worker_id"])


def downgrade() -> None:
    op.drop_index("ix_invocations_worker_id", table_name="invocations")
    op.drop_column("invocations", "cold_start")
    op.drop_column("invocations", "worker_id")
