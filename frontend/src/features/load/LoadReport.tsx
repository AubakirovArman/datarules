import { RefreshCw, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@shared/api";

type Props = {
  planId: string;
  refreshKey?: string;
  t: (key: string) => string;
};

export function LoadReport({ planId, refreshKey, t }: Props) {
  const [report, setReport] = useState<Record<string, unknown>>();
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      setReport(await api.loadPlanReport(planId));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh();
  }, [planId, refreshKey]);

  if (!report) return null;
  const destination = objectValue(report.destination);
  const preview = objectValue(report.preview);
  const verification = objectValue(report.live_verification) || objectValue(objectValue(report.agent).verification);
  const indexes = objectValue(verification.indexes);
  const target = objectValue(verification.target_table);
  const chunks = objectValue(verification.chunk_table);
  return (
    <div className="load-report">
      <div className="load-report-head">
        <strong><ShieldCheck size={15} /> {t("loadReport")}</strong>
        <button className="icon-button" disabled={busy} onClick={refresh} title={t("refresh")}>
          <RefreshCw size={14} />
        </button>
      </div>
      <span>{t("targetTable")}: {String(destination.schema_name ?? "")}.{String(destination.target_table ?? "")}</span>
      <span>{t("chunks")}: {String(destination.chunk_table ?? "")}</span>
      <span>{t("rows")}: {String(preview.loadable_rows ?? 0)} / {String(preview.rows ?? 0)}</span>
      {Object.keys(verification).length > 0 && (
        <>
          <span>{t("verificationReport")}: {String(verification.status ?? "")}</span>
          <small>{t("targetRecords")}: {String(target.inserted_records ?? 0)} / {String(target.total_rows ?? 0)}</small>
          <small>{t("chunks")}: {String(chunks.rows_for_plan ?? 0)} / {String(chunks.inserted_chunks ?? 0)}</small>
          <small>{t("indexes")}: FTS {mark(indexes.full_text)} · Vector {mark(indexes.vector)} · BM25 {mark(indexes.bm25)}</small>
        </>
      )}
    </div>
  );
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function mark(value: unknown) {
  return value ? "OK" : "ATTN";
}
