"""Add routes table and HTTP tracking fields to invocations.

Routes map HTTP method + path patterns to functions within a project.
The gateway endpoint uses these to dispatch incoming HTTP requests.

The invocation fields track whether a function was called directly
(via /api/invoke) or through the gateway, and which HTTP method/path
triggered it.

Revision ID: 005
Revises: 004
Create Date: 2026-02-15
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "005"
down_revision: Union[str, None] = "004"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "routes",
        sa.Column("id", sa.String(), primary_key=True),
        sa.Column(
            "project_id",
            sa.String(),
            sa.ForeignKey("projects.id"),
            nullable=False,
        ),
        sa.Column(
            "function_id",
            sa.String(),
            sa.ForeignKey("functions.id"),
            nullable=False,
        ),
        sa.Column("method", sa.String(), nullable=False),
        sa.Column("path", sa.String(), nullable=False),
        sa.Column("description", sa.String(), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.UniqueConstraint(
            "project_id", "method", "path", name="uq_route_project_method_path"
        ),
    )
    op.create_index("ix_routes_project_id", "routes", ["project_id"])
    op.create_index("ix_routes_function_id", "routes", ["function_id"])

    # Add gateway tracking fields to invocations.
    # source: "direct" (default) or "gateway"
    # http_method/http_path: filled when invoked via gateway
    op.add_column(
        "invocations",
        sa.Column("source", sa.String(), nullable=False, server_default="direct"),
    )
    op.add_column(
        "invocations",
        sa.Column("http_method", sa.String(), nullable=True),
    )
    op.add_column(
        "invocations",
        sa.Column("http_path", sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("invocations", "http_path")
    op.drop_column("invocations", "http_method")
    op.drop_column("invocations", "source")
    op.drop_index("ix_routes_function_id")
    op.drop_index("ix_routes_project_id")
    op.drop_table("routes")
