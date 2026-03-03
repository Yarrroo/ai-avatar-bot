"""add avatar greeting column

Revision ID: a1b2c3d4e5f6
Revises: 267cf7799f34
Create Date: 2026-03-03 20:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '267cf7799f34'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'avatars',
        sa.Column('greeting', sa.Text(), server_default='', nullable=False),
    )


def downgrade() -> None:
    op.drop_column('avatars', 'greeting')
