"""add_index_to_customer_business_id

Revision ID: 658b9447be77
Revises: 83ece8adc8df
Create Date: 2025-06-10 03:38:47.496577

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '658b9447be77'
down_revision: Union[str, None] = '83ece8adc8df'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass