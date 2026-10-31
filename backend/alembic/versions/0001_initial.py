"""initial schema: cases, evidence, extractions, passages, revisions, approvals, jobs, events, audit_events, claim_history, eval_runs

Revision ID: 0001
Revises:
"""
from alembic import op

from app.models import Base

revision = "0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # The initial migration materialises the models' tables. Later schema changes must be separate migrations.
    Base.metadata.create_all(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.drop_all(bind=op.get_bind())
