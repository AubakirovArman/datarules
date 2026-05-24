from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .db import Base


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


class Dataset(Base):
    __tablename__ = "datasets"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("ds"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(40), default="draft")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    documents: Mapped[list["Document"]] = relationship(back_populates="dataset")


class Document(Base):
    __tablename__ = "documents"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("doc"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    file_name: Mapped[str] = mapped_column(String(500), nullable=False)
    file_type: Mapped[str] = mapped_column(String(120), default="application/octet-stream")
    storage_path: Mapped[str] = mapped_column(Text, nullable=False)
    sha256: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(40), default="uploaded")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    dataset: Mapped[Dataset] = relationship(back_populates="documents")
    blocks: Mapped[list["DocumentBlock"]] = relationship(back_populates="document")


class DocumentBlock(Base):
    __tablename__ = "document_blocks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("blk"))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    page: Mapped[int | None] = mapped_column(Integer)
    sheet_name: Mapped[str | None] = mapped_column(String(200))
    slide_number: Mapped[int | None] = mapped_column(Integer)
    block_type: Mapped[str] = mapped_column(String(40), default="paragraph")
    text: Mapped[str] = mapped_column(Text, default="")
    table_json: Mapped[dict | list | None] = mapped_column(JSON)
    bbox: Mapped[list[float] | None] = mapped_column(JSON)
    confidence: Mapped[float] = mapped_column(Float, default=1.0)

    document: Mapped[Document] = relationship(back_populates="blocks")


class DocumentReview(Base):
    __tablename__ = "document_reviews"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("rev"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="needs_user_choice")
    reason: Mapped[str] = mapped_column(Text, default="")
    doc_type_options: Mapped[list[dict]] = mapped_column(JSON, default=list)
    table_options: Mapped[list[dict]] = mapped_column(JSON, default=list)
    selected_doc_type: Mapped[str | None] = mapped_column(String(120))
    selected_table: Mapped[str | None] = mapped_column(String(120))
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DocumentAiSummary(Base):
    __tablename__ = "document_ai_summaries"
    __table_args__ = (UniqueConstraint("document_id", name="uq_document_ai_summaries_document"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("sum"))
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    source_model: Mapped[str] = mapped_column(String(160), default="")
    summary_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DocumentExtractionRun(Base):
    __tablename__ = "document_extraction_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("xrun"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    document_id: Mapped[str] = mapped_column(ForeignKey("documents.id"), index=True)
    run_type: Mapped[str] = mapped_column(String(40), default="ingestion")
    status: Mapped[str] = mapped_column(String(40), default="completed")
    parser_version: Mapped[str] = mapped_column(String(80), default="datarules_v1")
    canonical_path: Mapped[str] = mapped_column(Text, default="")
    quality_json: Mapped[dict] = mapped_column(JSON, default=dict)
    metrics_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error_message: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class IngestionJob(Base):
    __tablename__ = "ingestion_jobs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("job"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="queued")
    total_files: Mapped[int] = mapped_column(Integer, default=0)
    processed_files: Mapped[int] = mapped_column(Integer, default=0)
    total_steps: Mapped[int] = mapped_column(Integer, default=8)
    completed_steps: Mapped[int] = mapped_column(Integer, default=0)
    current_stage: Mapped[str] = mapped_column(String(120), default="queued")
    error_message: Mapped[str | None] = mapped_column(Text)
    attempt_count: Mapped[int] = mapped_column(Integer, default=0)
    max_attempts: Mapped[int] = mapped_column(Integer, default=3)
    heartbeat_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class JobEvent(Base):
    __tablename__ = "job_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("evt"))
    job_id: Mapped[str] = mapped_column(ForeignKey("ingestion_jobs.id"), index=True)
    stage: Mapped[str] = mapped_column(String(120), nullable=False)
    message: Mapped[str] = mapped_column(Text, default="")
    progress_percent: Mapped[int] = mapped_column(Integer, default=0)
    payload_json: Mapped[dict | list | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SchemaProposal(Base):
    __tablename__ = "schema_proposals"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("sch"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="proposed")
    proposal_json: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class SchemaVersion(Base):
    __tablename__ = "schema_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("schv"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    proposal_id: Mapped[str | None] = mapped_column(ForeignKey("schema_proposals.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(40), default="active")
    schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class DatabaseConnection(Base):
    __tablename__ = "database_connections"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("dbc"))
    name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    sqlalchemy_url: Mapped[str] = mapped_column(Text, nullable=False)
    sqlalchemy_url_encrypted: Mapped[str | None] = mapped_column(Text)
    default_schema: Mapped[str] = mapped_column(String(120), default="public")
    is_internal: Mapped[bool] = mapped_column(Boolean, default=False)
    capabilities_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class TableCatalog(Base):
    __tablename__ = "table_catalogs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("tbl"))
    connection_id: Mapped[str] = mapped_column(ForeignKey("database_connections.id"), index=True)
    schema_name: Mapped[str] = mapped_column(String(120), default="public")
    table_name: Mapped[str] = mapped_column(String(160), nullable=False)
    description: Mapped[str] = mapped_column(Text, default="")
    columns_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    agent_profile_json: Mapped[dict] = mapped_column(JSON, default=dict)
    can_create_rows: Mapped[bool] = mapped_column(Boolean, default=False)
    last_introspected_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class LoadPlan(Base):
    __tablename__ = "load_plans"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("load"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    status: Mapped[str] = mapped_column(String(40), default="needs_confirmation")
    connection_id: Mapped[str | None] = mapped_column(String, index=True)
    schema_version_id: Mapped[str | None] = mapped_column(String, index=True)
    schema_name: Mapped[str] = mapped_column(String(120), default="public")
    target_mode: Mapped[str] = mapped_column(String(40), default="existing")
    target_table: Mapped[str] = mapped_column(String(160), nullable=False)
    schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    preview_rows: Mapped[list[dict]] = mapped_column(JSON, default=list)
    validation_issues: Mapped[list[dict]] = mapped_column(JSON, default=list)
    agent_preparation_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    events: Mapped[list["LoadPlanEvent"]] = relationship(back_populates="plan", order_by="LoadPlanEvent.created_at")


class LoadPlanEvent(Base):
    __tablename__ = "load_plan_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("levt"))
    load_plan_id: Mapped[str] = mapped_column(ForeignKey("load_plans.id"), index=True)
    action: Mapped[str] = mapped_column(String(80), nullable=False)
    message: Mapped[str] = mapped_column(Text, default="")
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    plan: Mapped[LoadPlan] = relationship(back_populates="events")


class AgentAnswer(Base):
    __tablename__ = "agent_answers"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("ans"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    query: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    confidence: Mapped[str] = mapped_column(String(40), default="low")
    retrieval_mode: Mapped[str] = mapped_column(String(80), default="hybrid_search")
    model_source: Mapped[str] = mapped_column(String(120), default="")
    prompt_version: Mapped[str] = mapped_column(String(120), default="")
    model_id: Mapped[str] = mapped_column(Text, default="")
    replay_of_answer_id: Mapped[str | None] = mapped_column(String, index=True)
    citations_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    grounding_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GoldenCheck(Base):
    __tablename__ = "golden_checks"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("gold"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_terms: Mapped[list[str]] = mapped_column(JSON, default=list)
    notes: Mapped[str] = mapped_column(Text, default="")
    last_result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GoldenProfile(Base):
    __tablename__ = "golden_profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("gprof"))
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    domain: Mapped[str] = mapped_column(String(120), default="general", index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    description: Mapped[str] = mapped_column(Text, default="")
    checks_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class GoldenEvaluationRun(Base):
    __tablename__ = "golden_evaluation_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("grun"))
    dataset_id: Mapped[str] = mapped_column(ForeignKey("datasets.id"), index=True)
    profile_id: Mapped[str | None] = mapped_column(String, index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending")
    total: Mapped[int] = mapped_column(Integer, default=0)
    passed: Mapped[int] = mapped_column(Integer, default=0)
    failed: Mapped[int] = mapped_column(Integer, default=0)
    score: Mapped[int] = mapped_column(Integer, default=0)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class AuditEvent(Base):
    __tablename__ = "audit_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: new_id("aud"))
    actor: Mapped[str] = mapped_column(String(120), default="system")
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    entity_type: Mapped[str] = mapped_column(String(80), default="")
    entity_id: Mapped[str] = mapped_column(String, default="")
    dataset_id: Mapped[str | None] = mapped_column(String, index=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
