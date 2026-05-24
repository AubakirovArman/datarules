from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class DatasetCreate(BaseModel):
    name: str
    description: str = ""


class DatasetOut(BaseModel):
    id: str
    name: str
    description: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentOut(BaseModel):
    id: str
    dataset_id: str
    file_name: str
    file_type: str
    sha256: str
    status: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class JobOut(BaseModel):
    id: str
    dataset_id: str
    status: str
    total_files: int
    processed_files: int
    total_steps: int
    completed_steps: int
    current_stage: str
    error_message: str | None
    attempt_count: int = 0
    max_attempts: int = 3
    heartbeat_at: datetime | None = None
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class EventOut(BaseModel):
    id: str
    job_id: str
    stage: str
    message: str
    progress_percent: int
    payload_json: Any
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class SchemaProposalOut(BaseModel):
    id: str
    dataset_id: str
    status: str
    proposal_json: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DocumentReviewOut(BaseModel):
    id: str
    dataset_id: str
    document_id: str
    status: str
    reason: str
    doc_type_options: list[dict[str, Any]]
    table_options: list[dict[str, Any]]
    selected_doc_type: str | None
    selected_table: str | None
    notes: str
    created_at: datetime
    updated_at: datetime
    file_name: str | None = None

    model_config = ConfigDict(from_attributes=True)


class DocumentReviewDecision(BaseModel):
    selected_doc_type: str
    selected_table: str
    notes: str = ""


class PageSummary(BaseModel):
    label: str
    blocks: int
    tables: int
    text_chars: int
    low_confidence_blocks: int
    semantic_summary: str = ""


class DocumentQualityOut(BaseModel):
    status: str
    extraction_score: int
    average_confidence: float
    low_confidence_blocks: int
    empty_blocks: int
    image_pages_pending: int
    table_blocks: int
    text_chars: int
    total_pages: int
    pages_with_text: int
    warnings: list[dict[str, Any]]


class DocumentSummaryOut(BaseModel):
    document_id: str
    file_name: str
    file_type: str
    status: str
    summary: str
    blocks: int
    pages: int
    sheets: list[str]
    slides: int
    tables: int
    image_pages: int
    text_chars: int
    page_summaries: list[PageSummary]
    quality_profile: DocumentQualityOut
    summary_source: str = "deterministic"
    ai_summary: dict[str, Any] = Field(default_factory=dict)


class SchemaChatRequest(BaseModel):
    message: str
    language: str | None = Field(default=None, pattern="^(ru|kk|en)$")


class SchemaChatResponse(BaseModel):
    assistant_message: str
    proposal_json: dict[str, Any]


class DatabaseConnectionCreate(BaseModel):
    name: str
    description: str = ""
    sqlalchemy_url: str
    default_schema: str = "public"


class DatabaseConnectionOut(BaseModel):
    id: str
    name: str
    description: str
    default_schema: str
    is_internal: bool
    capabilities_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class TableCatalogUpsert(BaseModel):
    connection_id: str
    schema_name: str = "public"
    table_name: str
    description: str = ""
    columns_json: list[dict[str, Any]] = Field(default_factory=list)
    agent_profile_json: dict[str, Any] = Field(default_factory=dict)
    can_create_rows: bool = False


class TableCatalogOut(TableCatalogUpsert):
    id: str
    last_introspected_at: datetime | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class DbIntrospectionOut(BaseModel):
    connection_id: str
    schemas: list[str]
    tables: list[TableCatalogOut]
    capabilities: dict[str, Any]


class SearchRequest(BaseModel):
    query: str
    limit: int = 10


class AskRequest(BaseModel):
    query: str
    limit: int = 8


class AskCitation(BaseModel):
    marker: str
    document_id: str
    block_id: str
    file_name: str
    block_type: str = "citation"
    page: int | None
    sheet_name: str | None
    target_table: str | None
    text: str
    score: float
    match_source: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class AskResponse(BaseModel):
    answer_id: str | None = None
    answer: str
    confidence: str
    citations: list[AskCitation]
    grounding: dict[str, Any] = Field(default_factory=dict)
    retrieval_mode: str
    model_source: str
    prompt_version: str = ""
    model_id: str = ""
    replay_of_answer_id: str | None = None


class AgentAnswerOut(BaseModel):
    id: str
    dataset_id: str
    query: str
    answer: str
    confidence: str
    retrieval_mode: str
    model_source: str
    prompt_version: str
    model_id: str
    replay_of_answer_id: str | None
    citations_json: list[dict[str, Any]]
    grounding_json: dict[str, Any] | None = Field(default_factory=dict)
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoadPlanPreviewUpdate(BaseModel):
    preview_rows: list[dict[str, Any]]


class LoadPlanEventOut(BaseModel):
    id: str
    load_plan_id: str
    action: str
    message: str
    payload_json: dict[str, Any]
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class LoadPlanOut(BaseModel):
    id: str
    dataset_id: str
    status: str
    connection_id: str | None
    schema_version_id: str | None
    schema_name: str
    target_mode: str
    target_table: str
    plan_schema: dict[str, Any] = Field(alias="schema_json")
    preview_rows: list[dict[str, Any]]
    validation_issues: list[dict[str, Any]]
    agent_preparation_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime
    events: list[LoadPlanEventOut] = Field(default_factory=list)

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SearchHit(BaseModel):
    document_id: str
    block_id: str
    file_name: str
    block_type: str
    page: int | None
    sheet_name: str | None
    slide_number: int | None
    text: str
    score: float
    match_source: str | None = None
    target_table: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
