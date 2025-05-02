"""add business phone number

Revision ID: 001
Revises: 
Create Date: 2024-03-21 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    op.add_column('businesses', sa.Column('business_phone_number', sa.String(), nullable=True))


def downgrade():
    op.drop_column('businesses', 'business_phone_number') 