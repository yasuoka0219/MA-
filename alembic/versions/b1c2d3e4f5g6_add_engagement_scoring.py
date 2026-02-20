"""add engagement scoring tables and lead columns

Revision ID: b1c2d3e4f5g6
Revises: add_password_hash
Create Date: 2026-02-20
"""
from alembic import op
import sqlalchemy as sa

revision = 'b1c2d3e4f5g6'
down_revision = 'add_password_hash'
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column('leads', sa.Column('engagement_score', sa.Integer(), nullable=False, server_default='0'))
    op.add_column('leads', sa.Column('last_engaged_at', sa.DateTime(timezone=True), nullable=True))
    op.add_column('leads', sa.Column('score_band', sa.String(10), nullable=True))
    op.add_column('leads', sa.Column('tracking_id', sa.String(64), nullable=True))
    op.create_index('ix_leads_score_band', 'leads', ['score_band'])
    op.create_index('ix_leads_tracking_id', 'leads', ['tracking_id'], unique=True)

    op.create_table(
        'engagement_events',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('lead_id', sa.Integer(), sa.ForeignKey('leads.id'), nullable=True, index=True),
        sa.Column('send_log_id', sa.Integer(), sa.ForeignKey('send_logs.id'), nullable=True, index=True),
        sa.Column('scenario_id', sa.Integer(), nullable=True),
        sa.Column('calendar_event_id', sa.Integer(), nullable=True),
        sa.Column('event_type', sa.String(50), nullable=False),
        sa.Column('url', sa.Text(), nullable=True),
        sa.Column('referrer', sa.Text(), nullable=True),
        sa.Column('meta_json', sa.Text(), nullable=True),
        sa.Column('occurred_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
    )
    op.create_index('ix_engagement_events_lead_occurred', 'engagement_events', ['lead_id', 'occurred_at'])
    op.create_index('ix_engagement_events_type_occurred', 'engagement_events', ['event_type', 'occurred_at'])

    op.create_table(
        'web_sessions',
        sa.Column('id', sa.Integer(), primary_key=True),
        sa.Column('tracking_id', sa.String(64), nullable=False, index=True),
        sa.Column('lead_id', sa.Integer(), sa.ForeignKey('leads.id'), nullable=True, index=True),
        sa.Column('started_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('last_seen_at', sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column('pageviews', sa.Integer(), default=1, nullable=False),
    )


def downgrade() -> None:
    op.drop_table('web_sessions')
    op.drop_index('ix_engagement_events_type_occurred', 'engagement_events')
    op.drop_index('ix_engagement_events_lead_occurred', 'engagement_events')
    op.drop_table('engagement_events')
    op.drop_index('ix_leads_tracking_id', 'leads')
    op.drop_index('ix_leads_score_band', 'leads')
    op.drop_column('leads', 'tracking_id')
    op.drop_column('leads', 'score_band')
    op.drop_column('leads', 'last_engaged_at')
    op.drop_column('leads', 'engagement_score')
