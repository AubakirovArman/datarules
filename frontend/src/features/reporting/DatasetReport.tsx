import { FileJson, RefreshCw, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@shared/api";

type Props = {
  datasetId?: string;
  refreshKey: string;
  t: (key: string) => string;
};

export function DatasetReport({ datasetId, refreshKey, t }: Props) {
  const [report, setReport] = useState<Record<string, unknown>>();
  const [scorecard, setScorecard] = useState<Record<string, unknown>>();
  const [busy, setBusy] = useState(false);

  async function refresh() {
    if (!datasetId) return;
    setBusy(true);
    try {
      const [nextReport, nextScorecard] = await Promise.all([
        api.datasetReport(datasetId),
        api.qualityScorecard(datasetId),
      ]);
      setReport(nextReport);
      setScorecard(nextScorecard);
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, [datasetId, refreshKey]);

  if (!datasetId || !report) return null;
  const counts = objectValue(report.counts);
  const documents = recordArray(report.documents);
  const routing = objectValue(report.routing);
  const retrieval = objectValue(report.retrieval);
  const loading = recordArray(report.loading);
  const actions = stringArray(report.next_actions);
  return (
    <section className="panel summary-panel">
      <div className="panel-head">
        <h2>{t("readiness")} · {t("loadReport")}</h2>
        <button className="icon-button" disabled={busy} onClick={refresh} title={t("refresh")}>
          <RefreshCw size={16} />
        </button>
      </div>
      <div className="metric-row">
        <Metric label={t("files")} value={counts.documents ?? 0} />
        <Metric label={t("blocks")} value={counts.blocks ?? 0} />
        <Metric label={t("routesConfirmed")} value={counts.routes_confirmed ?? 0} />
        <Metric label={t("routesPending")} value={counts.routes_pending ?? 0} />
        <Metric label={t("loaded")} value={counts.loaded_plans ?? 0} />
      </div>
      <div className="route-summary">
        <strong>{t("status")}: {String(report.status ?? "")}</strong>
        <span>{t("documentRouting")}: {String(routing.confirmed ?? 0)} / {String(routing.total ?? 0)}</span>
        <span>{t("search")}: {String(retrieval.ready ? t("ready") : t("notReady"))}</span>
      </div>
      {scorecard && <QualityScorecard value={scorecard} t={t} />}
      <div className="summary-list">
        {documents.slice(0, 6).map((document) => (
          <DocumentCard document={document} t={t} key={String(document.id)} />
        ))}
      </div>
      {loading.length > 0 && (
        <div className="ai-summary-list">
          <strong>{t("previewLoad")}</strong>
          {loading.slice(0, 4).map((plan) => (
            <span key={String(plan.id)}>
              {String(plan.destination)} · {String(plan.status)} · {t("rows")} {String(plan.loadable_rows ?? 0)} / {String(plan.rows ?? 0)}
            </span>
          ))}
        </div>
      )}
      {recordArray(retrieval.tables).length > 0 && (
        <div className="ai-summary-list">
          <strong>{t("agentTables")}</strong>
          {recordArray(retrieval.tables).map((table) => (
            <span key={String(table.plan_id)}>
              <ShieldCheck size={13} /> {String(table.table)} · {String(table.chunk_table ?? "")} · {searchModes(table, t)}
            </span>
          ))}
        </div>
      )}
      {actions.length > 0 && (
        <div className="ai-summary-list">
          <strong>{t("nextActions")}</strong>
          {actions.map((action) => <span key={action}>{t(action)}</span>)}
        </div>
      )}
    </section>
  );
}

function QualityScorecard({ value, t }: { value: Record<string, unknown>; t: Props["t"] }) {
  const checks = recordArray(value.checks);
  const blockers = recordArray(value.blockers);
  return (
    <div className="ai-summary-list">
      <strong>{t("qualityNotes")} · {String(value.score ?? 0)}% · {t(String(value.status ?? "pending"))}</strong>
      <div className="metric-row">
        {checks.slice(0, 8).map((check) => (
          <Metric key={String(check.key)} label={scoreLabel(check, t)} value={`${String(check.score ?? 0)}%`} />
        ))}
      </div>
      {blockers.length > 0 && (
        <span>
          {t("validation")}: {blockers.map((item) => `${String(item.key)}:${blockerText(item)}`).join(" · ")}
        </span>
      )}
    </div>
  );
}

function DocumentCard({ document, t }: { document: Record<string, unknown>; t: Props["t"] }) {
  const metrics = objectValue(document.metrics);
  const quality = objectValue(document.quality);
  const route = objectValue(document.route);
  const table = objectValue(route.recommended_table);
  const keyPoints = arrayValue(document.key_points).map(formatItem).filter(Boolean).slice(0, 3);
  return (
    <article className="summary-card">
      <div className="summary-title">
        <FileJson size={17} />
        <strong>{String(document.file_name ?? document.id ?? "")}</strong>
        <small>{String(document.status ?? "")} · {String(document.summary_source ?? "")}</small>
        <a className="icon-button" href={canonicalHref(document)} target="_blank" rel="noreferrer">
          {t("exportJson")}
        </a>
      </div>
      <p>{String(document.summary ?? "")}</p>
      <div className="metric-row">
        <Metric label={t("pages")} value={metrics.pages ?? 0} />
        <Metric label={t("tables")} value={metrics.tables ?? 0} />
        <Metric label={t("confidence")} value={`${String(quality.extraction_score ?? 0)}%`} />
      </div>
      <small>{t("targetTable")}: {String(route.selected_table ?? table.label ?? table.value ?? "")}</small>
      {keyPoints.length > 0 && <SummaryList title={t("keyPoints")} items={keyPoints} />}
    </article>
  );
}

function SummaryList({ title, items }: { title: string; items: string[] }) {
  return (
    <div className="ai-summary-list">
      <strong>{title}</strong>
      {items.map((item, index) => <span key={index}>{item}</span>)}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="metric">
      <strong>{String(value)}</strong>
      <span>{label}</span>
    </div>
  );
}

function searchModes(table: Record<string, unknown>, t: Props["t"]) {
  const modes = [];
  if (table.keyword_search) modes.push(t("keywordSearch"));
  if (table.semantic_search) modes.push(t("semanticSearch"));
  if (table.bm25) modes.push("BM25");
  return modes.length ? modes.join(" + ") : t("notReady");
}

function scoreLabel(check: Record<string, unknown>, t: Props["t"]) {
  const key = String(check.key ?? "");
  const map: Record<string, string> = {
    extraction: "readiness_extraction",
    gemma_summary: "gemmaSummary",
    routing: "readiness_routing",
    schema: "readiness_schema",
    preview: "readiness_preview",
    source_references: "routeSource",
    load: "readiness_materialization",
    retrieval: "readiness_retrieval",
    golden_answers: "answer",
  };
  return t(map[key] ?? key);
}

function blockerText(value: Record<string, unknown>) {
  const blockers = Array.isArray(value.blockers) ? value.blockers : [];
  return blockers.slice(0, 3).map(String).join(",");
}

function canonicalHref(document: Record<string, unknown>) {
  const path = String(document.canonical_json ?? "");
  return path.startsWith("/api/") ? path : `/api${path}`;
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function recordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item) => typeof item === "object") as Array<Record<string, unknown>> : [];
}

function arrayValue(value: unknown): unknown[] {
  return Array.isArray(value) ? value : [];
}

function stringArray(value: unknown): string[] {
  return Array.isArray(value) ? value.map(String) : [];
}

function formatItem(item: unknown) {
  if (typeof item === "string" || typeof item === "number") return String(item);
  if (!item || typeof item !== "object") return "";
  const value = item as Record<string, unknown>;
  return [value.name ?? value.title ?? value.entity, value.value ?? value.reason]
    .filter(Boolean)
    .map(String)
    .join(" — ");
}
