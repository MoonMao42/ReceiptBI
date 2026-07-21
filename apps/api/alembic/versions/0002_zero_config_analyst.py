"""zero config analyst workspace

Revision ID: 0002_zero_config_analyst
Revises: 0001_initial
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "0002_zero_config_analyst"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _uuid() -> sa.types.TypeEngine:
    return postgresql.UUID(as_uuid=True)


def _timestamps() -> list[sa.Column]:
    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    ]


def upgrade() -> None:
    op.create_table(
        "projects",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text()),
        sa.Column("status", sa.String(20), server_default="active", nullable=False),
        sa.Column("extra_data", sa.JSON(), server_default="{}", nullable=False),
        *_timestamps(),
    )
    op.create_index("ix_projects_status", "projects", ["status"])

    op.create_table(
        "project_data_sources",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("connection_id", _uuid()),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("format", sa.String(30)),
        sa.Column("source_uri", sa.Text()),
        sa.Column("working_uri", sa.Text()),
        sa.Column("fingerprint", sa.String(64)),
        sa.Column("status", sa.String(30), server_default="attached", nullable=False),
        sa.Column("profile_data", sa.JSON(), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["connection_id"], ["connections.id"], ondelete="SET NULL"),
        *_timestamps(),
    )
    op.create_index("ix_project_data_sources_project_id", "project_data_sources", ["project_id"])
    op.create_index("ix_project_data_sources_fingerprint", "project_data_sources", ["fingerprint"])

    op.create_table(
        "preflight_reports",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("data_source_id", _uuid(), nullable=False),
        sa.Column("status", sa.String(30), server_default="ready", nullable=False),
        sa.Column("summary", sa.Text(), server_default="", nullable=False),
        sa.Column("issues", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("ambiguities", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("inferred_schema", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("source_snapshot", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("fingerprint", sa.String(64)),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["data_source_id"], ["project_data_sources.id"], ondelete="CASCADE"
        ),
        *_timestamps(),
    )
    op.create_index("ix_preflight_reports_project_id", "preflight_reports", ["project_id"])
    op.create_index(
        "ix_preflight_reports_data_source_id", "preflight_reports", ["data_source_id"]
    )

    op.create_table(
        "sanitation_recipes",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("data_source_id", _uuid(), nullable=False),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("status", sa.String(30), server_default="applied", nullable=False),
        sa.Column("operations", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("input_fingerprint", sa.String(64)),
        sa.Column("output_fingerprint", sa.String(64)),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["data_source_id"], ["project_data_sources.id"], ondelete="CASCADE"
        ),
        *_timestamps(),
    )
    op.create_index("ix_sanitation_recipes_project_id", "sanitation_recipes", ["project_id"])

    op.create_table(
        "semantic_entries",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("key", sa.String(160), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("entry_type", sa.String(30), server_default="business_rule", nullable=False),
        sa.Column("state", sa.String(20), server_default="candidate", nullable=False),
        sa.Column("confidence", sa.Float(), server_default="0.5", nullable=False),
        sa.Column("evidence", sa.JSON(), server_default="[]", nullable=False),
        sa.Column("source", sa.String(30), server_default="inferred", nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("project_id", "key", name="uq_semantic_entry_project_key"),
        *_timestamps(),
    )
    op.create_index("ix_semantic_entries_project_id", "semantic_entries", ["project_id"])
    op.create_index("ix_semantic_entries_state", "semantic_entries", ["state"])

    op.create_table(
        "analysis_runs",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("conversation_id", _uuid()),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("state", sa.String(30), server_default="understanding", nullable=False),
        sa.Column("stage", sa.String(30), server_default="understanding", nullable=False),
        sa.Column("report", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("checkpoint", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("error", sa.Text()),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["conversation_id"], ["conversations.id"], ondelete="SET NULL"
        ),
        *_timestamps(),
    )
    op.create_index("ix_analysis_runs_project_id", "analysis_runs", ["project_id"])
    op.create_index("ix_analysis_runs_state", "analysis_runs", ["state"])

    op.create_table(
        "artifacts",
        sa.Column("id", _uuid(), primary_key=True),
        sa.Column("project_id", _uuid(), nullable=False),
        sa.Column("analysis_run_id", _uuid(), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("payload", sa.JSON(), server_default="{}", nullable=False),
        sa.Column("technical_details", sa.JSON(), server_default="{}", nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["analysis_run_id"], ["analysis_runs.id"], ondelete="CASCADE"),
        *_timestamps(),
    )
    op.create_index("ix_artifacts_project_id", "artifacts", ["project_id"])
    op.create_index("ix_artifacts_analysis_run_id", "artifacts", ["analysis_run_id"])


def downgrade() -> None:
    for table in (
        "artifacts",
        "analysis_runs",
        "semantic_entries",
        "sanitation_recipes",
        "preflight_reports",
        "project_data_sources",
        "projects",
    ):
        op.drop_table(table)
