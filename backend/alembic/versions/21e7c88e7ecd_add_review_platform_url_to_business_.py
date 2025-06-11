"""add_review_platform_url_to_business_profiles

Revision ID: 21e7c88e7ecd
Revises: 0f37aa60ba2b
Create Date: 2025-05-31 15:37:02.775139

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '21e7c88e7ecd'  # <<< --- PASTE THE NEWLY GENERATED ID HERE
down_revision: Union[str, None] = '0f37aa60ba2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# backend/alembic/versions/21e7c88e7ecd_add_review_platform_url_to_business_.py
def upgrade() -> None:
    # The 'review_platform_url' column is now expected to be created by
    # Base.metadata.create_all() based on the current BusinessProfile model
    # when setting up a new database or when Alembic's env.py reflects metadata.
    print("Migration 21e7c88e7ecd: Assuming 'review_platform_url' column is created by Base.metadata.create_all(). Skipping explicit op.add_column.")
    pass

def downgrade() -> None:
    # Correspondingly, if the column was created by Base.metadata,
    # this drop might not be what you want unless you're managing everything via diffs.
    print("Migration 21e7c88e7ecd: Assuming 'review_platform_url' column management is by Base.metadata. Skipping explicit op.drop_column.")
    pass
    # ### end Alembic commands ###