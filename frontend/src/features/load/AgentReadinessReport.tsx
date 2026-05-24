type Props = {
  value: Record<string, unknown>;
  t: (key: string) => string;
};

export function AgentReadinessReport({ value, t }: Props) {
  if (!value || Object.keys(value).length === 0) return null;
  const retrieval = objectValue(value.retrieval);
  const structured = objectValue(value.structured_load);
  const quality = objectValue(value.quality);
  const verification = objectValue(value.verification);
  const rowReview = objectValue(structured.row_review);
  const indexes = arrayValue(retrieval.planned_indexes);
  const chunkTable = retrieval.chunk_table ?? value.chunk_table ?? "";
  const lifecycle = indexLifecycle(value, retrieval, verification);
  return (
    <div className={`agent-plan ${value.ready_for_agent ? "ready" : "attention"}`}>
      <strong>{t("agentReadiness")} · {String(value.stage ?? "planned")}</strong>
      <span>{t("structuredRows")}: {String(structured.ready_rows ?? value.inserted_records ?? 0)} / {String(structured.preview_rows ?? "")}</span>
      <span>{t("rowReview")}: {reviewText(rowReview, t)}</span>
      <span>{t("retrievalPlan")}: {String(chunkTable)} · {String(retrieval.embedding_column ?? value.embedding_dimensions ?? "")}</span>
      {indexes.length > 0 && <small>{t("indexes")}: {indexes.join(", ")}</small>}
      <div className="index-lifecycle">
        {lifecycle.map((item) => (
          <small className={item.ready ? "ok" : "warning"} key={item.label}>
            <b>{item.label}</b>
            <span>{item.ready ? t("ready") : t(item.status)}</span>
          </small>
        ))}
      </div>
      {Boolean(quality.confidence) && <small>{t("confidence")}: {String(JSON.stringify(quality.confidence))}</small>}
      <VerificationReport value={verification} t={t} />
    </div>
  );
}

function VerificationReport({ value, t }: Props) {
  if (Object.keys(value).length === 0) return null;
  const target = objectValue(value.target_table);
  const chunk = objectValue(value.chunk_table);
  const embeddings = objectValue(value.embeddings);
  const indexes = objectValue(value.indexes);
  const checks = recordArray(value.checks);
  return (
    <div className="verification-report">
      <strong>{t("verificationReport")} · {String(value.status ?? "")}</strong>
      <span>{t("targetRecords")}: {String(target.inserted_records ?? 0)} / {String(target.total_rows ?? 0)}</span>
      <span>{t("chunks")}: {String(chunk.rows_for_plan ?? 0)} / {String(chunk.inserted_chunks ?? 0)}</span>
      <span>{t("embeddings")}: {String(embeddings.rows_with_embedding ?? 0)} / {String(embeddings.expected_rows ?? 0)}</span>
      <small>{t("indexes")}: FTS {mark(indexes.full_text)} · Vector {mark(indexes.vector)} · BM25 {mark(indexes.bm25)}</small>
      <div className="verification-checks">
        {checks.map((check) => (
          <small className={check.ok ? "ok" : "warning"} key={String(check.code)}>
            {mark(check.ok)} {String(check.code)}
          </small>
        ))}
      </div>
    </div>
  );
}

function reviewText(value: Record<string, unknown>, t: Props["t"]) {
  const parts = ["approved", "candidate", "needs_review", "rejected"]
    .map((key) => `${t(key)} ${String(value[key] ?? 0)}`);
  return parts.join(" · ");
}

function indexLifecycle(
  value: Record<string, unknown>,
  retrieval: Record<string, unknown>,
  verification: Record<string, unknown>,
) {
  const indexes = objectValue(verification.indexes);
  const embeddings = objectValue(verification.embeddings);
  const chunk = objectValue(verification.chunk_table);
  const stage = String(value.stage ?? "planned");
  const analysisOnly = value.analysis_only === true || value.target_mode === "analysis_only";
  return [
    { label: "Target", ready: analysisOnly || stage === "materialized", status: "readinessStatus_pending" },
    { label: "Chunks", ready: Boolean(chunk.rows_for_plan || value.inserted_chunks), status: "readinessStatus_pending" },
    { label: "Embeddings", ready: Boolean(embeddings.rows_with_embedding) || value.embedding_status === "ready", status: String(value.embedding_status || "readinessStatus_pending") },
    { label: "FTS", ready: Boolean(indexes.full_text), status: "readinessStatus_pending" },
    { label: "BM25", ready: Boolean(indexes.bm25) || Boolean(value.bm25), status: "readinessStatus_pending" },
  ];
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function arrayValue(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function recordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item) => typeof item === "object") as Array<Record<string, unknown>> : [];
}

function mark(value: unknown) {
  return value ? "OK" : "ATTN";
}
