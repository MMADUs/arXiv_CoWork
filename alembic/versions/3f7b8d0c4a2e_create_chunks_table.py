"""create chunks table

Revision ID: 3f7b8d0c4a2e
Revises: b98da81ccff5
Create Date: 2026-07-31 11:08:00.000000
"""

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa

revision: str = "3f7b8d0c4a2e"
down_revision: str | Sequence[str] | None = "b98da81ccff5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "chunks",
        sa.Column("id", sa.UUID(), nullable=False),
        sa.Column("paper_id", sa.UUID(), nullable=False),
        sa.Column("document_id", sa.String(length=128), nullable=True),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("section_title", sa.Text(), nullable=True),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("word_count", sa.Integer(), nullable=False),
        sa.Column("start_word", sa.Integer(), nullable=False),
        sa.Column("end_word", sa.Integer(), nullable=False),
        sa.Column("start_char", sa.Integer(), nullable=False),
        sa.Column("end_char", sa.Integer(), nullable=False),
        sa.Column("overlap_with_previous", sa.Integer(), nullable=False),
        sa.Column("overlap_with_next", sa.Integer(), nullable=False),
        sa.Column("source_object_key", sa.Text(), nullable=False),
        sa.Column("embedding_model", sa.String(length=128), nullable=True),
        sa.Column("embedding_dimension", sa.Integer(), nullable=True),
        sa.Column("embedding_error", sa.Text(), nullable=True),
        sa.Column("embedding_status", sa.String(length=32), nullable=False),
        sa.Column("indexing_status", sa.String(length=32), nullable=False),
        sa.Column("indexing_error", sa.Text(), nullable=True),
        sa.Column("embedded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("indexed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["paper_id"], ["papers.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_chunks_paper_id"), "chunks", ["paper_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_chunks_paper_id"), table_name="chunks")
    op.drop_table("chunks")
