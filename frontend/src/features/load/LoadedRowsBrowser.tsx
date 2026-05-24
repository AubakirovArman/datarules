import { Database, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@shared/api";

type Props = {
  planId: string;
  enabled: boolean;
  refreshKey?: string;
  t: (key: string) => string;
};

export function LoadedRowsBrowser({ planId, enabled, refreshKey, t }: Props) {
  const [payload, setPayload] = useState<Record<string, unknown>>();
  const [offset, setOffset] = useState(0);
  const [busy, setBusy] = useState(false);
  const limit = 10;

  async function refresh(nextOffset = offset) {
    if (!enabled) return;
    setBusy(true);
    try {
      setPayload(await api.loadedRows(planId, nextOffset, limit));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    setOffset(0);
    void refresh(0);
  }, [planId, enabled, refreshKey]);

  if (!enabled) return null;
  const rows = recordArray(payload?.rows);
  const total = Number(payload?.total ?? 0);
  return (
    <div className="loaded-rows">
      <div className="load-report-head">
        <strong><Database size={15} /> {t("loadedRows")}</strong>
        <button className="icon-button" disabled={busy} onClick={() => refresh()} title={t("refresh")}>
          <RefreshCw size={14} />
        </button>
      </div>
      <small>{t("rows")}: {rows.length} / {total}</small>
      <div className="loaded-row-list">
        {rows.map((row) => <LoadedRow row={row} t={t} key={String(row.id)} />)}
        {rows.length === 0 && <span className="empty">{t("no_rows")}</span>}
      </div>
      <div className="load-actions">
        <button disabled={offset <= 0 || busy} onClick={() => page(offset - limit)}>
          {t("back")}
        </button>
        <button disabled={offset + limit >= total || busy} onClick={() => page(offset + limit)}>
          {t("continue")}
        </button>
      </div>
    </div>
  );

  function page(nextOffset: number) {
    const normalized = Math.max(0, nextOffset);
    setOffset(normalized);
    void refresh(normalized);
  }
}

function LoadedRow({ row, t }: { row: Record<string, unknown>; t: Props["t"] }) {
  const fields = objectValue(row.field_values);
  const typed = objectValue(row.typed_columns);
  const source = objectValue(row.source);
  const evidence = String(source.evidence ?? "");
  const displayFields = Object.keys(fields).length ? fields : typed;
  return (
    <article className="loaded-row">
      <div className="summary-title">
        <strong>{String(fields.title ?? fields.name ?? row.id ?? "")}</strong>
        <small>{String(source.file_name ?? "")} · {source.page ? `${t("pages")} ${String(source.page)}` : ""}</small>
      </div>
      <p>{String(row.content ?? "")}</p>
      <div className="row-field-grid">
        {Object.entries(displayFields).slice(0, 8).map(([key, value]) => (
          <span key={key}><strong>{key}</strong>{String(value ?? "")}</span>
        ))}
      </div>
      {evidence && (
        <div className="route-evidence">
          <strong>{t("evidence")}</strong>
          <em>{evidence}</em>
        </div>
      )}
    </article>
  );
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function recordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item) => typeof item === "object") as Array<Record<string, unknown>> : [];
}
