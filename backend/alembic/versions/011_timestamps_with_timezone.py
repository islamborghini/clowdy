"""Store timestamps as TIMESTAMPTZ rather than naive local timestamps.

Every timestamp default is datetime.now(timezone.utc), which is timezone
aware. The columns were naive, which SQLite silently tolerated by dropping
the offset and Postgres rejects outright -- writing an invocation log failed
with "can't subtract offset-naive and offset-aware datetimes".

The naive column also reached the browser as an ISO string with no "Z", so
new Date() parsed it as local time and every timestamp in the UI rendered
shifted by the viewer's UTC offset.

Existing rows were all written as UTC, so the conversion just declares what
was already true.

SQLite has no native timestamp type and applies type affinity dynamically,
so there is nothing to alter there and this migration is a no-op on it.

Revision ID: 011
Revises: 010
Create Date: 2026-09-07
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "011"
down_revision: Union[str, None] = "010"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# (table, column) for every timestamp in the schema.
TIMESTAMP_COLUMNS = [
    ("projects", "created_at"),
    ("projects", "updated_at"),
    ("functions", "created_at"),
    ("functions", "updated_at"),
    ("function_versions", "created_at"),
    ("function_versions", "updated_at"),
    ("invocations", "created_at"),
    ("env_vars", "created_at"),
    ("env_vars", "updated_at"),
    ("routes", "created_at"),
    ("routes", "updated_at"),
]


def _convert(to_timezone: bool) -> None:
    if op.get_bind().dialect.name != "postgresql":
        return

    for table, column in TIMESTAMP_COLUMNS:
        op.alter_column(
            table,
            column,
            type_=sa.DateTime(timezone=to_timezone),
            # Existing values are UTC; say so explicitly rather than letting
            # Postgres assume the server's timezone.
            postgresql_using=f"{column} AT TIME ZONE 'UTC'",
        )


def upgrade() -> None:
    _convert(to_timezone=True)


def downgrade() -> None:
    _convert(to_timezone=False)
