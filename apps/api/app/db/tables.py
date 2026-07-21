"""数据库表定义"""

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import (
    JSON,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, UUIDMixin


class Connection(Base, UUIDMixin, TimestampMixin):
    """数据库连接表"""

    __tablename__ = "connections"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    driver: Mapped[str] = mapped_column(String(20), nullable=False)  # mysql, postgresql, sqlite
    host: Mapped[str | None] = mapped_column(String(255))
    port: Mapped[int | None] = mapped_column(Integer)
    username: Mapped[str | None] = mapped_column(String(100))
    password_encrypted: Mapped[str | None] = mapped_column(Text)
    database_name: Mapped[str | None] = mapped_column(String(100))
    extra_options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)


class Model(Base, UUIDMixin, TimestampMixin):
    """模型配置表"""

    __tablename__ = "models"

    name: Mapped[str] = mapped_column(String(100), nullable=False)
    provider: Mapped[str] = mapped_column(String(50), nullable=False)
    model_id: Mapped[str] = mapped_column(String(100), nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500))
    api_key_encrypted: Mapped[str | None] = mapped_column(Text)
    extra_options: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    # Credential presence and provider health are deliberately separate.  The
    # encrypted value may exist while being unreadable or rejected upstream;
    # health is evidence from a real completion request, not a storage flag.
    health_status: Mapped[str] = mapped_column(
        String(20), default="unknown", server_default="unknown"
    )
    last_checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error_category: Mapped[str | None] = mapped_column(String(30))
    last_response_time_ms: Mapped[int | None] = mapped_column(Integer)


class Conversation(Base, UUIDMixin, TimestampMixin):
    """对话表"""

    __tablename__ = "conversations"

    connection_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("connections.id", ondelete="SET NULL")
    )
    model_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("models.id", ondelete="SET NULL")
    )
    title: Mapped[str | None] = mapped_column(String(200))
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    extra_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation", cascade="all, delete-orphan", order_by="Message.created_at"
    )


class Message(Base, UUIDMixin):
    """消息表"""

    __tablename__ = "messages"

    conversation_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    role: Mapped[str] = mapped_column(String(20), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    extra_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow)

    conversation: Mapped["Conversation"] = relationship(back_populates="messages")


class AppSettings(Base, TimestampMixin):
    """单工作区设置表"""

    __tablename__ = "app_settings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, default=1)
    default_model_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("models.id", ondelete="SET NULL")
    )
    default_connection_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("connections.id", ondelete="SET NULL")
    )
    context_rounds: Mapped[int] = mapped_column(Integer, default=5)
    python_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    diagnostics_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_repair_enabled: Mapped[bool] = mapped_column(Boolean, default=True)


class Project(Base, UUIDMixin, TimestampMixin):
    """An isolated business analysis workspace."""

    __tablename__ = "projects"

    name: Mapped[str] = mapped_column(String(120), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    extra_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    data_sources: Mapped[list["ProjectDataSource"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    semantic_entries: Mapped[list["SemanticEntry"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    semantic_revisions: Mapped[list["SemanticEntryRevision"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )
    reports: Mapped[list["ReportDocument"]] = relationship(
        back_populates="project", cascade="all, delete-orphan"
    )


class ProjectDataSource(Base, UUIDMixin, TimestampMixin):
    """A file or database connection attached to a project."""

    __tablename__ = "project_data_sources"

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    connection_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("connections.id", ondelete="SET NULL")
    )
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    format: Mapped[str | None] = mapped_column(String(30))
    source_uri: Mapped[str | None] = mapped_column(Text)
    working_uri: Mapped[str | None] = mapped_column(Text)
    fingerprint: Mapped[str | None] = mapped_column(String(64), index=True)
    status: Mapped[str] = mapped_column(String(30), default="attached")
    profile_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    project: Mapped["Project"] = relationship(back_populates="data_sources")
    connection: Mapped["Connection | None"] = relationship()


class PreflightReportRecord(Base, UUIDMixin, TimestampMixin):
    """Stored, human-readable data readiness report."""

    __tablename__ = "preflight_reports"

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    data_source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("project_data_sources.id", ondelete="CASCADE"),
        index=True,
    )
    status: Mapped[str] = mapped_column(String(30), default="ready")
    summary: Mapped[str] = mapped_column(Text, default="")
    issues: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    ambiguities: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    inferred_schema: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    source_snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    fingerprint: Mapped[str | None] = mapped_column(String(64))


class SanitationRecipeRecord(Base, UUIDMixin, TimestampMixin):
    """Reversible data-cleaning operations for one source."""

    __tablename__ = "sanitation_recipes"

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    data_source_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("project_data_sources.id", ondelete="CASCADE")
    )
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    status: Mapped[str] = mapped_column(String(30), default="applied")
    operations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    input_fingerprint: Mapped[str | None] = mapped_column(String(64))
    output_fingerprint: Mapped[str | None] = mapped_column(String(64))
    # Application-enforced pointer: keeping this FK-free avoids a circular DDL
    # dependency while revision rows remain append-only.
    active_revision_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), index=True)


class SanitationRecipeRevisionRecord(Base, UUIDMixin):
    """Immutable cleaning history for a materialized sanitation recipe head."""

    __tablename__ = "sanitation_recipe_revisions"
    __table_args__ = (
        UniqueConstraint(
            "recipe_id",
            "revision_number",
            name="uq_sanitation_recipe_revision_number",
        ),
        CheckConstraint(
            "state IN ('candidate', 'confirmed', 'reverted')",
            name="ck_sanitation_recipe_revision_state",
        ),
    )

    recipe_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("sanitation_recipes.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_revision_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey(
            "sanitation_recipe_revisions.id",
            name="fk_sanitation_recipe_revisions_parent_revision_id",
            ondelete="NO ACTION",
            deferrable=True,
            initially="DEFERRED",
        ),
        index=True,
    )
    state: Mapped[str] = mapped_column(String(20), nullable=False)
    operations: Mapped[list[dict[str, Any]]] = mapped_column(JSON, nullable=False)
    input_contract: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    output_contract: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    actor_source: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    # Stored as durable provenance rather than an FK: deleting a correction must
    # not rewrite immutable cleaning history.
    source_correction_id: Mapped[str | None] = mapped_column(String(36), index=True)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)


class SemanticEntry(Base, UUIDMixin, TimestampMixin):
    """Three-level project knowledge: candidate, confirmed or locked."""

    __tablename__ = "semantic_entries"
    __table_args__ = (UniqueConstraint("project_id", "key", name="uq_semantic_entry_project_key"),)

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    key: Mapped[str] = mapped_column(String(160), nullable=False)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    entry_type: Mapped[str] = mapped_column(String(30), default="business_rule")
    state: Mapped[str] = mapped_column(String(20), default="candidate", index=True)
    confidence: Mapped[float] = mapped_column(Float, default=0.5)
    definition: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    validity: Mapped[str] = mapped_column(String(20), default="active")
    execution_state: Mapped[str] = mapped_column(String(30), default="definition_only")
    execution_details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    source: Mapped[str] = mapped_column(String(30), default="inferred")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    revision_number: Mapped[int] = mapped_column(Integer, default=0)
    # Kept as an application-enforced pointer to avoid a circular DDL dependency.
    # Semantic revisions are immutable, so a successfully written pointer cannot dangle
    # unless the whole project is removed.
    active_revision_id: Mapped[UUID | None] = mapped_column(PG_UUID(as_uuid=True), index=True)

    project: Mapped["Project"] = relationship(back_populates="semantic_entries")


class SemanticEntryRevision(Base, UUIDMixin):
    """Immutable semantic history; SemanticEntry remains the materialized read head."""

    __tablename__ = "semantic_entry_revisions"
    __table_args__ = (
        UniqueConstraint(
            "semantic_entry_id",
            "revision_number",
            name="uq_semantic_revision_entry_number",
        ),
    )

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    semantic_entry_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("semantic_entries.id", ondelete="RESTRICT"),
        index=True,
    )
    revision_number: Mapped[int] = mapped_column(Integer, nullable=False)
    parent_revision_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("semantic_entry_revisions.id", ondelete="RESTRICT"),
        index=True,
    )
    restored_from_revision_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("semantic_entry_revisions.id", ondelete="RESTRICT"),
        index=True,
    )
    mutation_kind: Mapped[str] = mapped_column(String(40), nullable=False)
    actor_source: Mapped[str] = mapped_column(String(30), nullable=False)
    reason: Mapped[str | None] = mapped_column(Text)
    source_correction_id: Mapped[str | None] = mapped_column(String(36), index=True)
    snapshot: Mapped[dict[str, Any]] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(default=datetime.utcnow, index=True)

    project: Mapped["Project"] = relationship(back_populates="semantic_revisions")


class AnalysisCorrection(Base, UUIDMixin, TimestampMixin):
    """A user correction tied to one report, optionally promoted to project knowledge."""

    __tablename__ = "analysis_corrections"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "analysis_run_id",
            "fingerprint",
            name="uq_analysis_correction_run_fingerprint",
        ),
    )

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    analysis_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    semantic_entry_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("semantic_entries.id", ondelete="SET NULL"), index=True
    )
    target_key: Mapped[str | None] = mapped_column(String(160), index=True)
    target_ref: Mapped[str | None] = mapped_column(String(96), index=True)
    correction_type: Mapped[str] = mapped_column(String(30), default="business_rule")
    text: Mapped[str] = mapped_column(Text, nullable=False)
    scope: Mapped[str] = mapped_column(String(20), default="run")
    state: Mapped[str] = mapped_column(String(20), default="recorded", index=True)
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    evidence: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)


class AnalysisRun(Base, UUIDMixin, TimestampMixin):
    """Persisted state for an autonomous analysis investigation."""

    __tablename__ = "analysis_runs"

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    conversation_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("conversations.id", ondelete="SET NULL")
    )
    query: Mapped[str] = mapped_column(Text, nullable=False)
    state: Mapped[str] = mapped_column(String(30), default="understanding", index=True)
    stage: Mapped[str] = mapped_column(String(30), default="understanding")
    report: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    checkpoint: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text)


class ArtifactRecord(Base, UUIDMixin, TimestampMixin):
    """Business artifact with technical evidence kept separately."""

    __tablename__ = "artifacts"

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    analysis_run_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("analysis_runs.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(30), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    technical_details: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class ReportDocument(Base, UUIDMixin, TimestampMixin):
    """An editable report assembled from manual and immutable analysis sources."""

    __tablename__ = "report_documents"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published', 'archived')",
            name="ck_report_document_status",
        ),
    )

    project_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True), ForeignKey("projects.id", ondelete="CASCADE"), index=True
    )
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    extra_data: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    project: Mapped["Project"] = relationship(back_populates="reports")
    pages: Mapped[list["ReportPage"]] = relationship(
        back_populates="report",
        cascade="all, delete-orphan",
        order_by="ReportPage.order_index",
    )


class ReportPage(Base, UUIDMixin, TimestampMixin):
    """One ordered page inside an editable report document."""

    __tablename__ = "report_pages"

    report_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("report_documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(160), nullable=False)
    order_index: Mapped[int] = mapped_column(Integer, default=0, index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)

    report: Mapped["ReportDocument"] = relationship(back_populates="pages")
    blocks: Mapped[list["ReportBlock"]] = relationship(
        back_populates="page",
        cascade="all, delete-orphan",
        order_by="ReportBlock.order_index",
    )


class ReportBlock(Base, UUIDMixin, TimestampMixin):
    """Editable report content whose original analysis records remain untouched."""

    __tablename__ = "report_blocks"
    __table_args__ = (
        CheckConstraint(
            "source_kind IN ('manual', 'analysis_run', 'artifact')",
            name="ck_report_block_source_kind",
        ),
    )

    page_id: Mapped[UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("report_pages.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    block_type: Mapped[str] = mapped_column(String(40), nullable=False)
    title: Mapped[str | None] = mapped_column(String(200))
    order_index: Mapped[int] = mapped_column(Integer, default=0, index=True)
    source_kind: Mapped[str] = mapped_column(String(20), nullable=False)
    analysis_run_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("analysis_runs.id", ondelete="SET NULL"),
        index=True,
    )
    artifact_id: Mapped[UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("artifacts.id", ondelete="SET NULL"),
        index=True,
    )
    # Durable provenance and source payload snapshot. The nullable FKs above
    # are only live links; this value survives normal investigation cleanup.
    source_ref: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    content: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    layout: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)

    page: Mapped["ReportPage"] = relationship(back_populates="blocks")
    analysis_run: Mapped["AnalysisRun | None"] = relationship()
    artifact: Mapped["ArtifactRecord | None"] = relationship()

    @property
    def source_available(self) -> bool:
        if self.source_kind == "manual":
            return True
        if self.source_kind == "analysis_run":
            return self.analysis_run_id is not None
        return self.artifact_id is not None
