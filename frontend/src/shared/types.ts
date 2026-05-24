export type Dataset = {
  id: string;
  name: string;
  description: string;
  status: string;
  created_at: string;
};

export type DocumentFile = {
  id: string;
  dataset_id: string;
  file_name: string;
  file_type: string;
  sha256: string;
  status: string;
  created_at: string;
};
export type Job = {
  id: string;
  dataset_id: string;
  status: string;
  total_files: number;
  processed_files: number;
  total_steps: number;
  completed_steps: number;
  current_stage: string;
  error_message?: string | null;
  attempt_count: number;
  max_attempts: number;
  heartbeat_at?: string | null;
  updated_at: string;
};
export type JobEvent = {
  id: string;
  stage: string;
  message: string;
  progress_percent: number;
  payload_json?: unknown;
  created_at: string;
};
export type SchemaProposal = {
  id: string;
  dataset_id: string;
  status: string;
  proposal_json: Record<string, unknown>;
  created_at: string;
};

export type ReviewOption = {
  value: string;
  label: string;
  confidence: number;
  reason?: string;
  signals?: string[];
  evidence?: string[];
  source?: string;
  connection_id?: string;
  schema_name?: string;
};

export type DocumentReview = {
  id: string;
  dataset_id: string;
  document_id: string;
  file_name?: string | null;
  status: string;
  reason: string;
  doc_type_options: ReviewOption[];
  table_options: ReviewOption[];
  selected_doc_type?: string | null;
  selected_table?: string | null;
  notes: string;
};

export type PageSummary = {
  label: string;
  blocks: number;
  tables: number;
  text_chars: number;
  low_confidence_blocks: number;
  semantic_summary: string;
};

export type DocumentSummary = {
  document_id: string;
  file_name: string;
  file_type: string;
  status: string;
  summary: string;
  blocks: number;
  pages: number;
  sheets: string[];
  slides: number;
  tables: number;
  image_pages: number;
  text_chars: number;
  page_summaries: PageSummary[];
  quality_profile: DocumentQuality;
  summary_source: string;
  ai_summary: Record<string, unknown>;
};

export type DocumentQuality = {
  status: string;
  extraction_score: number;
  average_confidence: number;
  low_confidence_blocks: number;
  empty_blocks: number;
  image_pages_pending: number;
  table_blocks: number;
  text_chars: number;
  total_pages: number;
  pages_with_text: number;
  warnings: Array<Record<string, unknown>>;
};

export type SchemaChatResponse = {
  assistant_message: string;
  proposal_json: Record<string, unknown>;
};

export type DbConnection = {
  id: string;
  name: string;
  description: string;
  default_schema: string;
  is_internal: boolean;
  capabilities_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
};

export type TableCatalog = {
  id: string;
  connection_id: string;
  schema_name: string;
  table_name: string;
  description: string;
  columns_json: Array<Record<string, unknown>>;
  agent_profile_json: Record<string, unknown>;
  can_create_rows: boolean;
  last_introspected_at?: string | null;
};

export type ReadinessStage = {
  key: string;
  status: "ready" | "attention" | "pending" | "blocked";
  count?: number;
  total?: number;
};

export type AgentTableReadiness = {
  plan_id: string;
  schema_name: string;
  target_table: string;
  chunk_table?: string | null;
  inserted_records: number;
  inserted_chunks: number;
  embedding_status?: string | null;
  semantic_search: boolean;
  bm25: boolean;
  keyword_search: boolean;
  ready_for_agent: boolean;
};

export type DatasetReadiness = {
  dataset_id: string;
  status: string;
  score: number;
  counts: Record<string, number | string | boolean>;
  stages: ReadinessStage[];
  action_plan: ReadinessAction[];
  agent: {
    ready: boolean;
    loaded_plans: number;
    tables: AgentTableReadiness[];
  };
  next_actions: string[];
};

export type ReadinessAction = {
  code: string;
  severity: "blocker" | "warning" | "ready";
  step: string;
  title_key: string;
  detail_key: string;
  cta_key: string;
  load_plan_id?: string | null;
};

export type DiagnosticCheck = {
  key: string;
  status: "ok" | "warning" | "failed" | "disabled";
  latency_ms: number;
  details: Record<string, unknown>;
};

export type RuntimeDiagnostics = {
  status: "ok" | "attention" | "failed";
  checks: DiagnosticCheck[];
  runtime: Record<string, unknown>;
};

export type LoadPlan = {
  id: string;
  dataset_id: string;
  status: string;
  connection_id?: string | null;
  schema_version_id?: string | null;
  schema_name: string;
  target_mode: string;
  target_table: string;
  schema_json: Record<string, unknown>;
  preview_rows: Array<Record<string, unknown>>;
  validation_issues: Array<Record<string, unknown>>;
  agent_preparation_json: Record<string, unknown>;
  created_at: string;
  updated_at: string;
  events: LoadPlanEvent[];
};

export type LoadPlanEvent = {
  id: string;
  load_plan_id: string;
  action: string;
  message: string;
  payload_json: Record<string, unknown>;
  created_at: string;
};

export type SearchHit = {
  document_id: string;
  block_id: string;
  file_name: string;
  block_type: string;
  page?: number | null;
  sheet_name?: string | null;
  slide_number?: number | null;
  text: string;
  score: number;
  match_source?: string | null;
  target_table?: string | null;
  metadata?: Record<string, unknown>;
};

export type AskCitation = {
  marker: string;
  document_id: string;
  block_id: string;
  file_name: string;
  block_type?: string;
  page?: number | null;
  sheet_name?: string | null;
  target_table?: string | null;
  text: string;
  score: number;
  match_source?: string | null;
  metadata?: Record<string, unknown>;
};

export type AskResponse = {
  answer_id?: string | null;
  answer: string;
  confidence: string;
  citations: AskCitation[];
  grounding: Record<string, unknown>;
  retrieval_mode: string;
  model_source: string;
  prompt_version: string;
  model_id: string;
  replay_of_answer_id?: string | null;
};

export type AnswerHistory = {
  id: string;
  dataset_id: string;
  query: string;
  answer: string;
  confidence: string;
  retrieval_mode: string;
  model_source: string;
  prompt_version: string;
  model_id: string;
  replay_of_answer_id?: string | null;
  citations_json: AskCitation[];
  grounding_json?: Record<string, unknown> | null;
  created_at: string;
};

export type AuditEvent = {
  id: string;
  actor: string;
  action: string;
  entity_type: string;
  entity_id: string;
  dataset_id?: string | null;
  payload_json: Record<string, unknown>;
  created_at?: string | null;
};
