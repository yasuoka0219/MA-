"""add_send_logs_unique_constraint

Revision ID: eb4d2695eac7
Revises: 045d801f097e
Create Date: 2025-12-22 09:36:09.059248

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eb4d2695eac7'
down_revision: Union[str, Sequence[str], None] = '045d801f097e'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_unique_constraint(
        'uq_send_logs_lead_scenario_scheduled',
        'send_logs',
        ['lead_id', 'scenario_id', 'scheduled_for']
    )


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_send_logs_lead_scenario_scheduled', 'send_logs', type_='unique')
