"""fix sent_at timestamps

Revision ID: fix_sent_at_timestamps
Revises: # will be set by alembic
Create Date: 2024-03-21 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa
from datetime import datetime, timezone

# revision identifiers, used by Alembic.
revision = 'fix_sent_at_timestamps'
down_revision = None  # will be set by alembic
branch_labels = None
depends_on = None

def upgrade():
    # Get connection
    conn = op.get_bind()

    # Update messages where status='sent' but sent_at is NULL
    conn.execute("""
        UPDATE messages 
        SET sent_at = created_at,
            status = 'sent'
        WHERE status = 'sent' 
        AND sent_at IS NULL
        AND message_type = 'scheduled'
    """)

    # Update messages where sent_at is set but status isn't 'sent'
    conn.execute("""
        UPDATE messages
        SET status = 'sent'
        WHERE sent_at IS NOT NULL
        AND status != 'sent'
        AND message_type = 'scheduled'
    """)

    # Update engagements where status='sent' but sent_at is NULL
    conn.execute("""
        UPDATE engagements
        SET sent_at = created_at
        WHERE status = 'sent'
        AND sent_at IS NULL
    """)

    # Update engagements where sent_at is set but status isn't 'sent'
    conn.execute("""
        UPDATE engagements
        SET status = 'sent'
        WHERE sent_at IS NOT NULL
        AND status != 'sent'
    """)

def downgrade():
    # This migration is data fixing only, no schema changes to revert
    pass 