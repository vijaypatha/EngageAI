"""add business phone number

Revision ID: 001
Revises: 
Create Date: 2024-03-21 10:00:00.000000

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = '001'
down_revision = 'base_initial_base_revision'
branch_labels = None
depends_on = None


# backend/alembic/versions/001_add_business_phone_number.py
def upgrade():
    # The business_phone_number column is now created directly by Base.metadata.create_all
    # based on the current BusinessProfile model, so this operation is redundant for new DB setups.
    # op.add_column('business_profiles', sa.Column('business_phone_number', sa.String(), nullable=True))
    pass # Add pass if no other operations in upgrade

def downgrade():
    # Correspondingly, if the column was created by Base.metadata,
    # this drop might not be what you want unless you're managing everything via diffs.
    # For a clean build, this also becomes less relevant if the model dictates the initial state.
    # op.drop_column('business_profiles', 'business_phone_number')
    pass # Add pass if no other operations in downgrade