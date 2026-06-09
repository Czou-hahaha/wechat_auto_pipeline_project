"""initial schema for event enhancement"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "001_initial"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "articles",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("url", sa.Text(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("body_text", sa.Text(), nullable=True),
        sa.Column("source_host", sa.String(255), nullable=False, server_default=""),
        sa.Column("source_tier", sa.String(64), nullable=False, server_default=""),
        sa.Column("embedding", sa.LargeBinary(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_articles_url", "articles", ["url"], unique=True)
    op.create_index("ix_articles_created_at", "articles", ["created_at"])

    op.create_table(
        "events",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("dominant_topic_key", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("first_seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("importance_score", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("article_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_expansion_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("expansion_attempts", sa.Integer(), nullable=False, server_default="0"),
    )
    op.create_index("ix_events_importance_score", "events", ["importance_score"])
    op.create_index("ix_events_created_at", "events", ["created_at"])
    op.create_index("ix_events_first_seen_at", "events", ["first_seen_at"])

    op.create_table(
        "event_article_map",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="CASCADE"), nullable=False),
        sa.Column("article_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("articles.id", ondelete="CASCADE"), nullable=False),
        sa.Column("role", sa.String(32), nullable=False, server_default="support"),
        sa.Column("similarity_to_centroid", sa.Float(), nullable=True),
        sa.Column("added_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    )
    op.create_index("ix_event_article_map_event", "event_article_map", ["event_id"])
    op.create_index("ix_event_article_map_article", "event_article_map", ["article_id"])
    op.create_unique_constraint("uq_event_article", "event_article_map", ["event_id", "article_id"])

    op.create_table(
        "expansion_log",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("event_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("events.id", ondelete="SET NULL"), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("queries_json", postgresql.JSONB(), nullable=True),
        sa.Column("candidates_fetched", sa.Integer(), server_default="0"),
        sa.Column("candidates_passed_similarity", sa.Integer(), server_default="0"),
        sa.Column("articles_inserted", sa.Integer(), server_default="0"),
        sa.Column("error_detail", sa.Text(), nullable=True),
    )
    op.create_index("ix_expansion_log_event", "expansion_log", ["event_id"])


def downgrade() -> None:
    op.drop_table("expansion_log")
    op.drop_table("event_article_map")
    op.drop_table("events")
    op.drop_table("articles")
