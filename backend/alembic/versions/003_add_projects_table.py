"""Add projects table and project_id FK on functions.

Revision ID: 003
Revises: 002
Create Date: 2026-02-15
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "003"
down_revision: Union[str, None] = "002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column("user_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(), nullable=False),
        sa.Column("slug", sa.String(), nullable=False, unique=True),
        sa.Column("description", sa.String(), server_default=""),
        sa.Column("status", sa.String(), server_default="active"),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
    )
    op.create_index(op.f("ix_projects_user_id"), "projects", ["user_id"])
    op.create_index(op.f("ix_projects_name"), "projects", ["name"])

    op.add_column(
        "functions", sa.Column("project_id", sa.String(), nullable=True)
    )
    op.create_index(
        op.f("ix_functions_project_id"), "functions", ["project_id"]
    )
    # SQLite doesn't support ADD FOREIGN KEY after table creation, so we
    # rely on the application layer for referential integrity. The FK is
    # defined in the SQLAlchemy model for new databases created from scratch.


def downgrade() -> None:
    op.drop_index(op.f("ix_functions_project_id"), table_name="functions")
    op.drop_column("functions", "project_id")
    op.drop_index(op.f("ix_projects_name"), table_name="projects")
    op.drop_index(op.f("ix_projects_user_id"), table_name="projects")
    op.drop_table("projects")
