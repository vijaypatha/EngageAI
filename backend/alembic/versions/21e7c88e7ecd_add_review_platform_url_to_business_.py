"""add_review_platform_url_to_business_profiles

Revision ID: 21e7c88e7ecd
Revises: 0f37aa60ba2b
Create Date: 2025-05-31 15:37:02.775139

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '21e7c88e7ecd'
down_revision: Union[str, None] = '0f37aa60ba2b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('business_profiles', sa.Column('review_platform_url', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('business_profiles', 'review_platform_url')