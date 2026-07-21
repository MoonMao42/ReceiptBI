"""add editable report documents, pages and blocks

Revision ID: 0015_editable_reports
Revises: 0014_candidate_hygiene
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0015_editable_reports"
down_revision: str | None = "0014_candidate_hygiene"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.types.TypeEngine:
    return postgresql.UUID(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    ]


def upgrade() -> None:
    op.create_table(
        "report_documents",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(20), nullable=False, server_default="draft"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("extra_data", sa.JSON(), nullable=False, server_default="{}"),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_report_document_status",
        ),
        *_timestamps(),
    )
    op.create_index(
        "ix_report_documents_project_id",
        "report_documents",
        ["project_id"],
    )
    op.create_index("ix_report_documents_status", "report_documents", ["status"])

    op.create_table(
        "report_pages",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("report_id", _uuid(), nullable=False),
        sa.Column("title", sa.String(160), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(
            ["report_id"],
            ["report_documents.id"],
            ondelete="CASCADE",
        ),
        *_timestamps(),
    )
    op.create_index("ix_report_pages_report_id", "report_pages", ["report_id"])
    op.create_index("ix_report_pages_order_index", "report_pages", ["order_index"])

    op.create_table(
        "report_blocks",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("page_id", _uuid(), nullable=False),
        sa.Column("block_type", sa.String(40), nullable=False),
        sa.Column("title", sa.String(200)),
        sa.Column("order_index", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("source_kind", sa.String(20), nullable=False),
        sa.Column("analysis_run_id", _uuid()),
        sa.Column("artifact_id", _uuid()),
        sa.Column("source_ref", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("content", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("layout", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("config", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
        sa.ForeignKeyConstraint(["page_id"], ["report_pages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["analysis_run_id"],
            ["analysis_runs.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["artifact_id"], ["artifacts.id"], ondelete="SET NULL"),
        sa.CheckConstraint(
            "source_kind IN ('manual', 'analysis_run', 'artifact')",
            name="ck_report_block_source_kind",
        ),
        *_timestamps(),
    )
    op.create_index("ix_report_blocks_page_id", "report_blocks", ["page_id"])
    op.create_index("ix_report_blocks_order_index", "report_blocks", ["order_index"])
    op.create_index(
        "ix_report_blocks_analysis_run_id",
        "report_blocks",
        ["analysis_run_id"],
    )
    op.create_index("ix_report_blocks_artifact_id", "report_blocks", ["artifact_id"])


def downgrade() -> None:
    op.drop_table("report_blocks")
    op.drop_table("report_pages")
    op.drop_table("report_documents")
