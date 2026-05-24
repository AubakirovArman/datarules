import { AlertTriangle, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@shared/api";

type Props = {
  planId: string;
  refreshKey?: string;
  t: (key: string) => string;
};

export function LoadQuarantinePanel({ planId, refreshKey, t }: Props) {
  const [report, setReport] = useState<Record<string, unknown>>();
  const [busy, setBusy] = useState(false);
  async function refresh() {
    setBusy(true);
    try {
      setReport(await api.loadPlanQuarantine(planId));
    } finally {
      setBusy(false);
    }
  }
  useEffect(() => {
    void refresh();
  }, [planId, refreshKey]);
  if (!report) return null;
  const summary = objectValue(report.summary);
  const rows = recordArray(report.rows);
  if (!rows.length) return <div className="quarantine-panel ready"><strong>{title(t)}</strong><span>{emptyLabel(t)}</span></div>;
  return (
    <div className="quarantine-panel attention">
      <div className="quarantine-head">
        <strong><AlertTriangle size={15} /> {title(t)}</strong>
        <button className="icon-button" disabled={busy} onClick={refresh} title={t("refresh")}><RefreshCw size={14} /></button>
      </div>
      <span>{summaryLabel(t)}: {String(summary.quarantined_rows ?? 0)} / {String(summary.total_rows ?? 0)}</span>
      <div className="quarantine-grid">
        {rows.slice(0, 4).map((row) => (
          <div className="quarantine-row" key={String(row.row_id)}>
            <strong>{String(row.source_file ?? "")}</strong>
            <small>{String(row.row_status ?? "")} · {reasons(row).join(", ")}</small>
            <p>{String(row.content ?? "")}</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function title(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "Quarantine жолдары";
  if (language === "Language") return "Quarantine rows";
  return "Quarantine строк";
}

function emptyLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "Проблемалық жол жоқ.";
  if (language === "Language") return "No problematic rows.";
  return "Проблемных строк нет.";
}

function summaryLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "блокталған";
  if (language === "Language") return "blocked";
  return "заблокировано";
}

function reasons(row: Record<string, unknown>) {
  return Array.isArray(row.reasons) ? row.reasons.map(String) : [];
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function recordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item) => typeof item === "object") as Array<Record<string, unknown>> : [];
}
