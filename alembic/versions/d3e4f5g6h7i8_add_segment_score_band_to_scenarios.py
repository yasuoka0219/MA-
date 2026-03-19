"""add segment_score_band to scenarios

Revision ID: d3e4f5g6h7i8
Revises: c2d3e4f5g6h7
Create Date: 2026-03-11
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d3e4f5g6h7i8"
down_revision: Union[str, Sequence[str], None] = "c2d3e4f5g6h7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column("scenarios", sa.Column("segment_score_band", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("scenarios", "segment_score_band")

