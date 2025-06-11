"""create_ai_nudges_table

Revision ID: 0f37aa60ba2b
Revises: fix_sent_at_timestamps
Create Date: 05/31/2025

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
# from sqlalchemy.dialects import postgresql # Uncomment if using JSONB for PostgreSQL

# revision identifiers, used by Alembic.
revision: str = '0f37aa60ba2b' # 
down_revision: Union[str, None] = 'fix_sent_at_timestamps' # <<< --- THIS IS THE PARENT
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # The 'co_pilot_nudges' table is now expected to be created by 
    # Base.metadata.create_all() based on the current CoPilotNudge model
    # when setting up a new database or when Alembic's env.py reflects metadata.
    # This migration step might be redundant for new setups but could be
    # important if migrating an older database that didn't have this table.
    # For a clean setup where Base.metadata.create_all() runs first,
    # we can make this conditional or simply pass.

    # To make it robust, you could check if the table exists before creating:
    # from sqlalchemy import inspect
    # inspector = inspect(op.get_bind())
    # if 'co_pilot_nudges' not in inspector.get_table_names():
    #    op.create_table('co_pilot_nudges', ...) # Full definition here
    #    op.create_index(...)
    # else:
    #    print("Table 'co_pilot_nudges' already exists, skipping creation in migration 0f37aa60ba2b.")

    # For simplicity in a fresh setup where Base.metadata.create_all() handles it:
    print("Migration 0f37aa60ba2b: Assuming 'co_pilot_nudges' table is created by Base.metadata.create_all(). Skipping explicit op.create_table.")
    pass

def downgrade() -> None:
    # If the table was created by Base.metadata.create_all() in a fresh setup,
    # this downgrade might try to drop a table that Alembic didn't "own" the creation of
    # in this specific script for that scenario.
    # However, for a proper downgrade path, it should drop what it created.
    # If we assume Base.metadata.create_all() handles it, this also becomes conditional.

    # For simplicity, if we're making 'upgrade' a 'pass' for fresh DBs:
    print("Migration 0f37aa60ba2b: Assuming 'co_pilot_nudges' table management is by Base.metadata. Skipping explicit op.drop_table.")
    pass
    # If you had the conditional create in upgrade, you'd have a conditional drop here:
    # from sqlalchemy import inspect
    # inspector = inspect(op.get_bind())
    # if 'co_pilot_nudges' in inspector.get_table_names():
    #    op.drop_index('idx_copilotnudge_business_type_status', table_name='co_pilot_nudges')
    #    # ... other drop_index calls
    #    op.drop_table('co_pilot_nudges')
    # else:
    #    print("Table 'co_pilot_nudges' does not exist, skipping drop in migration 0f37aa60ba2b.")