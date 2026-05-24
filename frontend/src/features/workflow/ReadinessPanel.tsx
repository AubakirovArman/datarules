import { Activity, AlertTriangle, CheckCircle2, CircleDashed, Database, RefreshCw, Search } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@shared/api";
import type { DatasetReadiness, ReadinessAction, ReadinessStage } from "@shared/types";

type Props = {
  datasetId?: string;
  refreshKey: string;
  onNavigate?: (step: string, action?: ReadinessAction) => void;
  t: (key: string) => string;
};

export function ReadinessPanel({ datasetId, refreshKey, onNavigate, t }: Props) {
  const [value, setValue] = useState<DatasetReadiness>();
  const [reconciliation, setReconciliation] = useState<Record<string, unknown>>();

  async function refresh() {
    if (!datasetId) return;
    setValue(await api.readiness(datasetId));
    setReconciliation(await api.reconciliation(datasetId));
  }

  useEffect(() => {
    void refresh();
  }, [datasetId, refreshKey]);

  if (!datasetId || !value) return null;
  return (
    <section className={`readiness-panel ${value.status}`}>
      <div className="readiness-head">
        <div>
          <span className="workflow-title">{t("readiness")}</span>
          <strong>{t(value.status)} · {value.score}%</strong>
        </div>
        <button className="icon-button" onClick={refresh} title={t("refresh")}>
          <RefreshCw size={15} />
        </button>
      </div>
      <div className="readiness-meter"><span style={{ width: `${value.score}%` }} /></div>
      <div className="readiness-stages">
        {value.stages.map((stage) => <StageChip stage={stage} t={t} key={stage.key} />)}
      </div>
      <div className="readiness-body">
        <div>
          <strong><Database size={15} /> {t("agentTables")}</strong>
          {value.agent.tables.length === 0 && <small>{t("noAgentTables")}</small>}
          {value.agent.tables.slice(0, 3).map((table) => (
            <small key={table.plan_id}>
              {table.schema_name}.{table.target_table} · {table.chunk_table} · {searchModes(table, t)}
            </small>
          ))}
        </div>
        <div>
          <strong><Activity size={15} /> {t("nextActions")}</strong>
          {value.next_actions.length === 0 && <small className="ok">OK</small>}
          {value.next_actions.map((action) => <small key={action}>{t(action)}</small>)}
        </div>
      </div>
      <Reconciliation value={reconciliation} t={t} />
      <div className="readiness-action-plan">
        {value.action_plan?.slice(0, 4).map((action) => (
          <ActionCard action={action} onNavigate={onNavigate} t={t} key={action.code} />
        ))}
      </div>
    </section>
  );
}

function Reconciliation({ value, t }: { value?: Record<string, unknown>; t: Props["t"] }) {
  if (!value) return null;
  const counts = objectValue(value.counts);
  const plans = recordArray(value.plans);
  return (
    <div className="readiness-body">
      <div>
        <strong><Search size={15} /> {t("verificationReport")}</strong>
        <small>{t(String(value.status ?? "pending"))} · {t("agentTables")} {String(counts.loaded_plans ?? 0)}</small>
        {plans.slice(0, 3).map((plan) => (
          <small className={plan.status === "ready" ? "ok" : "warning"} key={String(plan.plan_id)}>
            {String(plan.schema_name)}.{String(plan.target_table)} · {String(plan.status)}
            {issueText(plan) ? ` · ${issueText(plan)}` : ""}
          </small>
        ))}
      </div>
    </div>
  );
}

function StageChip({ stage, t }: { stage: ReadinessStage; t: Props["t"] }) {
  return (
    <div className={`readiness-stage ${stage.status}`}>
      {icon(stage.status)}
      <strong>{t(`readiness_${stage.key}`)}</strong>
      <small>{[t(`readinessStatus_${stage.status}`), detailText(stage, t)].filter(Boolean).join(" · ")}</small>
    </div>
  );
}

function icon(status: ReadinessStage["status"]) {
  if (status === "ready") return <CheckCircle2 size={15} />;
  if (status === "blocked") return <AlertTriangle size={15} />;
  if (status === "attention") return <Activity size={15} />;
  return <CircleDashed size={15} />;
}

function ActionCard({
  action,
  onNavigate,
  t,
}: {
  action: ReadinessAction;
  onNavigate?: Props["onNavigate"];
  t: Props["t"];
}) {
  return (
    <button className={`readiness-action ${action.severity}`} onClick={() => onNavigate?.(action.step, action)} type="button">
      <strong>{t(action.title_key)}</strong>
      <small>{t(action.detail_key)}</small>
      <span>{t(action.cta_key)} · {action.step}</span>
    </button>
  );
}

function searchModes(table: DatasetReadiness["agent"]["tables"][number], t: Props["t"]) {
  const modes = [];
  if (table.keyword_search) modes.push(t("keywordSearch"));
  if (table.semantic_search) modes.push(t("semanticSearch"));
  if (table.bm25) modes.push("BM25");
  return modes.length ? modes.join(" + ") : t("notReady");
}

function detailText(stage: ReadinessStage, t: Props["t"]) {
  if (typeof stage.count !== "number") return "";
  if (typeof stage.total === "number") return `${stage.count} / ${stage.total}`;
  const unit: Record<string, string> = {
    upload: t("files"),
    extraction: t("blocks"),
    summary: t("gemmaSummary"),
    routing: t("documentRouting"),
    schema: t("schema"),
    preview: t("rows"),
    materialization: t("rows"),
    retrieval: t("agentTables"),
  };
  return `${stage.count} ${unit[stage.key] ?? ""}`.trim();
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function recordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item) => typeof item === "object") as Array<Record<string, unknown>> : [];
}

function issueText(plan: Record<string, unknown>) {
  const catalog = Array.isArray(plan.catalog_issues) ? plan.catalog_issues : [];
  const failures = Array.isArray(plan.critical_failures) ? plan.critical_failures : [];
  return [...catalog, ...failures].slice(0, 3).map(String).join(", ");
}
