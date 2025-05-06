"""add account_login

Revision ID: a1a39eaf1fec
Revises: 
Create Date: 2025-05-05 23:56:57.940168

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = 'a1a39eaf1fec'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

def upgrade() -> None:
    """Upgrade schema."""
    op.add_column('trades', sa.Column('account_login', sa.String(length=50), nullable=True))

def downgrade() -> None:
    """Downgrade schema."""
    op.drop_column('trades', 'account_login')
