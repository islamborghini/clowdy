"""Add requirements_txt and requirements_hash to projects.

These columns let each project store pip dependencies (as a
requirements.txt string) and a hash of the content for cache
invalidation when building custom Docker images.

Revision ID: 006
Revises: 005
Create Date: 2026-02-16
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "006"
down_revision: Union[str, None] = "005"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "projects",
        sa.Column("requirements_txt", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "projects",
        sa.Column("requirements_hash", sa.String(), nullable=False, server_default=""),
    )


def downgrade() -> None:
    op.drop_column("projects", "requirements_hash")
    op.drop_column("projects", "requirements_txt")
