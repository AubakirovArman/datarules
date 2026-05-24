import { Database, PlayCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "@shared/api";

type Props = {
  datasetId?: string;
  disabled: boolean;
  t: (key: string) => string;
};

export function StructuredSqlPane({ datasetId, disabled, t }: Props) {
  const [guide, setGuide] = useState<Record<string, unknown>>();
  const [planId, setPlanId] = useState("");
  const [sql, setSql] = useState("");
  const [result, setResult] = useState<Record<string, unknown>>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const tables = useMemo(() => recordArray(guide?.tables).filter((item) => item.status === "loaded"), [guide]);

  useEffect(() => {
    if (!datasetId) return;
    void api.queryGuide(datasetId, languageValue()).then((value) => {
      setGuide(value);
      const first = recordArray(value.tables).find((item) => item.status === "loaded");
      if (first) {
        setPlanId(String(first.plan_id ?? ""));
        setSql((current) => current || `select * from ${String(first.table)} limit 20`);
      }
    });
  }, [datasetId]);

  async function run() {
    if (!datasetId) return;
    setBusy(true);
    setError("");
    try {
      setResult(await api.sqlQuery(datasetId, sql, planId || undefined, 100));
    } catch (err) {
      setError(sqlErrorText(err, t));
    } finally {
      setBusy(false);
    }
  }

  if (!datasetId) return null;
  const columns = stringArray(result?.columns);
  const rows = recordArray(result?.rows);
  return (
    <div className="structured-sql">
      <div className="load-report-head">
        <strong><Database size={15} /> {t("structuredSql")}</strong>
        <small>{t("sqlReadOnlyHint")}</small>
      </div>
      {tables.length === 0 && <span className="empty">{t("noSqlTables")}</span>}
      {tables.length > 0 && (
        <>
          <select value={planId} onChange={(event) => choosePlan(event.target.value)}>
            {tables.map((table) => (
              <option value={String(table.plan_id)} key={String(table.plan_id)}>
                {String(table.schema)}.{String(table.table)}
              </option>
            ))}
          </select>
          <textarea value={sql} onChange={(event) => setSql(event.target.value)} placeholder={t("sqlPlaceholder")} />
          <button disabled={disabled || busy || !sql.trim()} onClick={run} type="button">
            <PlayCircle size={16} />
            <span>{t("runSql")}</span>
          </button>
        </>
      )}
      {error && <div className="error-banner">{error}</div>}
      {rows.length > 0 && (
        <div className="sql-result">
          <small>{t("sqlRows")}: {rows.length}</small>
          <div className="sql-table">
            <div className="sql-row head">{columns.map((column) => <strong key={column}>{column}</strong>)}</div>
            {rows.slice(0, 20).map((row, index) => (
              <div className="sql-row" key={index}>
                {columns.map((column) => <span key={column}>{formatValue(row[column])}</span>)}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );

  function choosePlan(id: string) {
    setPlanId(id);
    const table = tables.find((item) => String(item.plan_id) === id);
    if (table) setSql(`select * from ${String(table.table)} limit 20`);
  }
}

function recordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item) => typeof item === "object") as Array<Record<string, unknown>> : [];
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function formatValue(value: unknown) {
  if (value === null || value === undefined) return "";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
}

function sqlErrorText(err: unknown, t: Props["t"]) {
  const message = err instanceof Error ? err.message : String(err);
  if (message.includes("Confirm the load plan") || message.includes("No loaded tables")) return t("noSqlTables");
  return message;
}

function languageValue() {
  const value = localStorage.getItem("datarules-language") || "ru";
  return ["ru", "kk", "en"].includes(value) ? value : "ru";
}
