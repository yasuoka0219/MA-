"""add calendar events and registrations

Revision ID: a1b2c3d4e5f6
Revises: f1e28bda950c
Create Date: 2026-01-19 10:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, Sequence[str], None] = 'f1e28bda950c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""
    op.create_table('calendar_events',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('event_type', sa.String(length=50), nullable=False),
        sa.Column('title', sa.String(length=255), nullable=False),
        sa.Column('event_date', sa.Date(), nullable=False),
        sa.Column('location', sa.String(length=255), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint('id')
    )
    op.create_index(op.f('ix_calendar_events_event_type'), 'calendar_events', ['event_type'], unique=False)
    op.create_index(op.f('ix_calendar_events_event_date'), 'calendar_events', ['event_date'], unique=False)
    
    op.create_table('lead_event_registrations',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('lead_id', sa.Integer(), nullable=False),
        sa.Column('calendar_event_id', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False, server_default='scheduled'),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['lead_id'], ['leads.id'], ),
        sa.ForeignKeyConstraint(['calendar_event_id'], ['calendar_events.id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('lead_id', 'calendar_event_id', name='uq_lead_calendar_event')
    )
    op.create_index(op.f('ix_lead_event_registrations_lead_id'), 'lead_event_registrations', ['lead_id'], unique=False)
    op.create_index(op.f('ix_lead_event_registrations_calendar_event_id'), 'lead_event_registrations', ['calendar_event_id'], unique=False)
    
    op.add_column('scenarios', sa.Column('base_date_type', sa.String(length=20), nullable=True))
    op.execute("UPDATE scenarios SET base_date_type = 'lead_created_at' WHERE base_date_type IS NULL")
    op.alter_column('scenarios', 'base_date_type', nullable=False, server_default='lead_created_at')
    op.add_column('scenarios', sa.Column('event_type_filter', sa.String(length=50), nullable=True))
    op.add_column('scenarios', sa.Column('target_calendar_event_id', sa.Integer(), nullable=True))
    op.create_foreign_key('fk_scenarios_target_calendar_event', 'scenarios', 'calendar_events', ['target_calendar_event_id'], ['id'])
    
    op.add_column('send_logs', sa.Column('calendar_event_id', sa.Integer(), nullable=True))
    op.create_index(op.f('ix_send_logs_calendar_event_id'), 'send_logs', ['calendar_event_id'], unique=False)
    op.create_foreign_key('fk_send_logs_calendar_event', 'send_logs', 'calendar_events', ['calendar_event_id'], ['id'])
    
    op.execute("ALTER TABLE send_logs DROP CONSTRAINT IF EXISTS uq_lead_scenario_event")
    op.create_unique_constraint('uq_lead_scenario_calendar_event', 'send_logs', ['lead_id', 'scenario_id', 'calendar_event_id'])


def downgrade() -> None:
    """Downgrade schema."""
    op.drop_constraint('uq_lead_scenario_calendar_event', 'send_logs', type_='unique')
    op.drop_constraint('fk_send_logs_calendar_event', 'send_logs', type_='foreignkey')
    op.drop_index(op.f('ix_send_logs_calendar_event_id'), table_name='send_logs')
    op.drop_column('send_logs', 'calendar_event_id')
    
    op.drop_constraint('fk_scenarios_target_calendar_event', 'scenarios', type_='foreignkey')
    op.drop_column('scenarios', 'target_calendar_event_id')
    op.drop_column('scenarios', 'event_type_filter')
    op.drop_column('scenarios', 'base_date_type')
    
    op.drop_index(op.f('ix_lead_event_registrations_calendar_event_id'), table_name='lead_event_registrations')
    op.drop_index(op.f('ix_lead_event_registrations_lead_id'), table_name='lead_event_registrations')
    op.drop_table('lead_event_registrations')
    
    op.drop_index(op.f('ix_calendar_events_event_date'), table_name='calendar_events')
    op.drop_index(op.f('ix_calendar_events_event_type'), table_name='calendar_events')
    op.drop_table('calendar_events')
