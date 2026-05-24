import type {
  AskResponse,
  AuditEvent,
  AnswerHistory,
  Dataset,
  DatasetReadiness,
  DbConnection,
  DocumentFile,
  DocumentReview,
  DocumentSummary,
  Job,
  JobEvent,
  LoadPlan,
  RuntimeDiagnostics,
  SchemaProposal,
  SchemaChatResponse,
  SearchHit,
  TableCatalog,
} from "@shared/types";

const API = "/api";

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API}${path}`, {
    headers: init?.body instanceof FormData ? undefined : { "Content-Type": "application/json" },
    ...init,
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return response.json() as Promise<T>;
}

async function errorMessage(response: Response) {
  const body = await response.text();
  if (!body) return response.statusText || `HTTP ${response.status}`;
  try {
    return readableError(JSON.parse(body), response.statusText);
  } catch {
    return body;
  }
}

function readableError(value: unknown, fallback: string): string {
  if (typeof value === "string") return value;
  if (Array.isArray(value)) return value.map((item) => readableError(item, fallback)).filter(Boolean).join("; ");
  if (!value || typeof value !== "object") return fallback;
  const record = value as Record<string, unknown>;
  if (record.detail) return readableError(record.detail, fallback);
  if (record.message) return String(record.message);
  if (record.msg) return [locationText(record.loc), record.msg].filter(Boolean).join(": ");
  if (record.code) return [record.code, record.reason].filter(Boolean).join(": ");
  return fallback;
}

function locationText(value: unknown) {
  return Array.isArray(value) ? value.map(String).join(".") : "";
}

export const api = {
  health: () => json<Record<string, unknown>>("/health"),
  diagnostics: () => json<RuntimeDiagnostics>("/diagnostics"),
  datasets: () => json<Dataset[]>("/datasets"),
  datasetReport: (datasetId: string) => json<Record<string, unknown>>(`/datasets/${datasetId}/report`),
  qualityScorecard: (datasetId: string) => json<Record<string, unknown>>(`/datasets/${datasetId}/quality-scorecard`),
  queryGuide: (datasetId: string, language = "ru") =>
    json<Record<string, unknown>>(`/datasets/${datasetId}/query-guide?language=${language}`),
  sqlQuery: (datasetId: string, sql: string, plan_id?: string, limit = 100) =>
    json<Record<string, unknown>>(`/datasets/${datasetId}/sql-query`, {
      method: "POST",
      body: JSON.stringify({ sql, plan_id, limit }),
    }),
  readiness: (datasetId: string) => json<DatasetReadiness>(`/datasets/${datasetId}/readiness`),
  reconciliation: (datasetId: string) => json<Record<string, unknown>>(`/datasets/${datasetId}/reconciliation`),
  createDataset: (name: string, description: string) =>
    json<Dataset>("/datasets", { method: "POST", body: JSON.stringify({ name, description }) }),
  files: (datasetId: string) => json<DocumentFile[]>(`/datasets/${datasetId}/files`),
  upload: (datasetId: string, files: FileList) => {
    const body = new FormData();
    Array.from(files).forEach((file) => body.append("files", file));
    return json<DocumentFile[]>(`/datasets/${datasetId}/files`, { method: "POST", body });
  },
  deleteFile: (datasetId: string, documentId: string) =>
    json<{ status: string; document_id: string }>(`/datasets/${datasetId}/files/${documentId}`, {
      method: "DELETE",
    }),
  repairDocument: (datasetId: string, documentId: string) =>
    json<Record<string, unknown>>(`/datasets/${datasetId}/files/${documentId}/repair-extraction`, { method: "POST" }),
  extractionRuns: (datasetId: string, documentId: string) =>
    json<Record<string, unknown>>(`/datasets/${datasetId}/files/${documentId}/extraction-runs`),
  extractionRunDiff: (datasetId: string, documentId: string, runId: string) =>
    json<Record<string, unknown>>(`/datasets/${datasetId}/files/${documentId}/extraction-runs/${runId}/diff`),
  rollbackExtractionRun: (datasetId: string, documentId: string, runId: string) =>
    json<Record<string, unknown>>(`/datasets/${datasetId}/files/${documentId}/extraction-runs/${runId}/rollback`, { method: "POST" }),
  startJob: (datasetId: string) =>
    json<Job>(`/datasets/${datasetId}/ingestion-jobs`, { method: "POST" }),
  cancelJob: (jobId: string) =>
    json<Job>(`/jobs/${jobId}/cancel`, { method: "POST" }),
  job: (jobId: string) => json<Job>(`/jobs/${jobId}`),
  events: (jobId: string) => json<JobEvent[]>(`/jobs/${jobId}/events`),
  proposals: (datasetId: string) =>
    json<SchemaProposal[]>(`/datasets/${datasetId}/schema-proposals`),
  schemaVersions: (datasetId: string) =>
    json<Array<Record<string, unknown>>>(`/datasets/${datasetId}/schema-versions`),
  reviews: (datasetId: string) => json<DocumentReview[]>(`/datasets/${datasetId}/document-reviews`),
  acceptRecommendedReviews: (datasetId: string) =>
    json<DocumentReview[]>(`/datasets/${datasetId}/document-reviews/accept-recommended`, { method: "POST" }),
  summaries: (datasetId: string, language?: string) =>
    json<DocumentSummary[]>(`/datasets/${datasetId}/document-summaries?language=${safeLanguage(language)}`),
  documentQuality: (datasetId: string) =>
    json<Record<string, unknown>>(`/datasets/${datasetId}/document-quality`),
  decideReview: (reviewId: string, selected_doc_type: string, selected_table: string, notes: string) =>
    json<DocumentReview>(`/document-reviews/${reviewId}/decision`, {
      method: "POST",
      body: JSON.stringify({ selected_doc_type, selected_table, notes }),
    }),
  approve: (proposalId: string) =>
    json<SchemaProposal>(`/schema-proposals/${proposalId}/approve`, { method: "POST" }),
  schemaChat: (datasetId: string, message: string, language?: string) =>
    json<SchemaChatResponse>(`/datasets/${datasetId}/schema-chat`, {
      method: "POST",
      body: JSON.stringify({ message, language: safeLanguage(language) }),
    }),
  connections: () => json<DbConnection[]>("/database-connections"),
  createConnection: (name: string, description: string, sqlalchemy_url: string, default_schema: string) =>
    json<DbConnection>("/database-connections", {
      method: "POST",
      body: JSON.stringify({ name, description, sqlalchemy_url, default_schema }),
    }),
  introspectConnection: (connectionId: string) =>
    json<{ tables: TableCatalog[] }>(`/database-connections/${connectionId}/introspect`, { method: "POST" }),
  testConnection: (connectionId: string) =>
    json<Record<string, unknown>>(`/database-connections/${connectionId}/test`, { method: "POST" }),
  updateWritePolicy: (connectionId: string, enabled: boolean, schemas: string[], confirm_external_write = false) =>
    json<DbConnection>(`/database-connections/${connectionId}/write-policy`, {
      method: "PATCH",
      body: JSON.stringify({ enabled, schemas, confirm_external_write }),
    }),
  tableCatalog: () => json<TableCatalog[]>("/table-catalog"),
  loadPlans: (datasetId: string) => json<LoadPlan[]>(`/datasets/${datasetId}/load-plans`),
  loadPlanReport: (planId: string) => json<Record<string, unknown>>(`/load-plans/${planId}/report`),
  loadPlanQuarantine: (planId: string) => json<Record<string, unknown>>(`/load-plans/${planId}/quarantine`),
  loadedRows: (planId: string, offset = 0, limit = 25) =>
    json<Record<string, unknown>>(`/load-plans/${planId}/rows?offset=${offset}&limit=${limit}`),
  previewRowSource: (planId: string, rowId: string) =>
    json<Record<string, unknown>>(`/load-plans/${planId}/preview-rows/${encodeURIComponent(rowId)}/source`),
  createLoadPlan: (
    datasetId: string,
    connection_id: string | undefined,
    schema_name: string,
    target_mode: string,
    target_table: string,
    schema_json?: Record<string, unknown>,
    document_ids?: string[],
    schema_version_id?: string,
  ) =>
    json<LoadPlan>(`/datasets/${datasetId}/load-plans`, {
      method: "POST",
      body: JSON.stringify({ connection_id, schema_name, target_mode, target_table, schema_json, document_ids, schema_version_id }),
    }),
  confirmLoadPlan: (planId: string) =>
    json<LoadPlan>(`/load-plans/${planId}/confirm`, { method: "POST" }),
  rebuildLoadPlan: (planId: string) =>
    json<LoadPlan>(`/load-plans/${planId}/rebuild-preview`, { method: "POST" }),
  loadPlanPreviewDiff: (planId: string) =>
    json<Record<string, unknown>>(`/load-plans/${planId}/preview-diff`),
  reindexLoadPlan: (planId: string) =>
    json<LoadPlan>(`/load-plans/${planId}/reindex`, { method: "POST" }),
  updateLoadPlanRows: (planId: string, preview_rows: Array<Record<string, unknown>>) =>
    json<LoadPlan>(`/load-plans/${planId}/preview-rows`, {
      method: "PATCH",
      body: JSON.stringify({ preview_rows }),
    }),
  search: (datasetId: string, query: string) =>
    json<SearchHit[]>(`/datasets/${datasetId}/search`, {
      method: "POST",
      body: JSON.stringify({ query, limit: 12 }),
    }),
  ask: (datasetId: string, query: string) =>
    json<AskResponse>(`/datasets/${datasetId}/ask`, {
      method: "POST",
      body: JSON.stringify({ query, limit: 8 }),
    }),
  answerHistory: (datasetId: string) => json<AnswerHistory[]>(`/datasets/${datasetId}/answers`),
  replayAnswer: (answerId: string) =>
    json<AskResponse>(`/agent-answers/${answerId}/replay`, { method: "POST" }),
  goldenChecks: (datasetId: string) => json<Array<Record<string, unknown>>>(`/datasets/${datasetId}/golden-checks`),
  exportGoldenChecks: (datasetId: string) => json<Record<string, unknown>>(`/datasets/${datasetId}/golden-checks/export`),
  importGoldenChecks: (datasetId: string, profile: Record<string, unknown>) =>
    json<Record<string, unknown>>(`/datasets/${datasetId}/golden-checks/import`, {
      method: "POST",
      body: JSON.stringify(profile),
    }),
  createGoldenCheck: (datasetId: string, question: string, expected_terms: string) =>
    json<Record<string, unknown>>(`/datasets/${datasetId}/golden-checks`, {
      method: "POST",
      body: JSON.stringify({ question, expected_terms }),
    }),
  runGoldenChecks: (datasetId: string) =>
    json<Record<string, unknown>>(`/datasets/${datasetId}/golden-checks/run`, { method: "POST" }),
  goldenRuns: (datasetId: string) => json<Array<Record<string, unknown>>>(`/datasets/${datasetId}/golden-runs`),
  goldenGate: (datasetId: string) => json<Record<string, unknown>>(`/datasets/${datasetId}/golden-gate`),
  deleteGoldenCheck: (checkId: string) =>
    json<Record<string, unknown>>(`/golden-checks/${checkId}`, { method: "DELETE" }),
  goldenProfiles: () => json<Array<Record<string, unknown>>>("/golden-profiles"),
  saveGoldenProfile: (datasetId: string, name: string, domain: string, description = "") =>
    json<Record<string, unknown>>(`/datasets/${datasetId}/golden-profiles`, {
      method: "POST",
      body: JSON.stringify({ name, domain, description }),
    }),
  applyGoldenProfile: (datasetId: string, profileId: string, replace = false) =>
    json<Record<string, unknown>>(`/datasets/${datasetId}/golden-profiles/${profileId}/apply`, {
      method: "POST",
      body: JSON.stringify({ replace }),
    }),
  auditEvents: (limit = 40) => json<AuditEvent[]>(`/audit-events?limit=${limit}`),
};

function languageValue() {
  const value = localStorage.getItem("datarules-language") || "ru";
  return safeLanguage(value);
}

function safeLanguage(value?: string) {
  value = value || "ru";
  return ["ru", "kk", "en"].includes(value) ? value : "ru";
}
