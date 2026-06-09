"""Align PostgreSQL schema with V3 ArticleRecord / EventRecord for sync + audit."""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "002_align_v3"
down_revision = "001_initial"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("events", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("events", sa.Column("summary_zh", sa.Text(), nullable=True))

    op.add_column("articles", sa.Column("source_url", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("resolved_url", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("summary", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("summary_zh", sa.Text(), nullable=True))
    op.add_column("articles", sa.Column("status", sa.String(64), nullable=True))
    op.add_column("articles", sa.Column("topic_key", sa.String(128), nullable=True))
    op.create_index("ix_articles_status", "articles", ["status"], unique=False)
    op.create_index("ix_articles_topic_key", "articles", ["topic_key"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_articles_topic_key", table_name="articles")
    op.drop_index("ix_articles_status", table_name="articles")
    op.drop_column("articles", "topic_key")
    op.drop_column("articles", "status")
    op.drop_column("articles", "summary_zh")
    op.drop_column("articles", "summary")
    op.drop_column("articles", "resolved_url")
    op.drop_column("articles", "source_url")
    op.drop_column("events", "summary_zh")
    op.drop_column("events", "summary")
