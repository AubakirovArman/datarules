import { CheckCircle2, DatabaseZap, Eye, Search } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "@shared/api";
import type { LoadPlan, TableCatalog } from "@shared/types";
import type { SimpleFlowProps, SimpleStep } from "./types";
import {
  DestinationMode,
  latestPlan,
  planMatches,
  schemaJsonFromProposal,
  suggestedColumns,
  suggestedTable,
} from "./simpleFlowState";

type Props = {
  flow: SimpleFlowProps;
  onStep: (step: SimpleStep) => void;
};

export function SimpleDestinationPanel({ flow, onStep }: Props) {
  const defaultConnection = flow.connections.find((item) => item.is_internal) ?? flow.connections[0];
  const [mode, setMode] = useState<DestinationMode>("new");
  const [connectionId, setConnectionId] = useState(defaultConnection?.id ?? "");
  const [schema, setSchema] = useState(defaultConnection?.default_schema ?? "public");
  const [table, setTable] = useState(suggestedTable(flow.proposals));
  const plan = flow.loadPlans.find((item) => planMatches(item, mode, schema, table)) ?? latestPlan(flow.loadPlans);
  const [localPlan, setLocalPlan] = useState<LoadPlan>();
  const activePlan = planMatches(localPlan, mode, schema, table)
    ? localPlan
    : planMatches(plan, mode, schema, table)
      ? plan
      : undefined;
  const [existingKey, setExistingKey] = useState("");
  const [busy, setBusy] = useState("");
  const existingTables = useMemo(() => flow.tables.map(tableOption), [flow.tables]);

  useEffect(() => setTable(suggestedTable(flow.proposals)), [flow.proposals]);
  useEffect(() => setLocalPlan(undefined), [plan?.id, plan?.updated_at]);

  async function buildPreview() {
    if (!flow.datasetId) return;
    setBusy("preview");
    try {
      await prepareAiPlan(flow, mode);
      const target = mode === "analysis_only" ? "analysis_only" : table.trim();
      const next = await flow.onCreateLoadPlan(
        connectionId || undefined,
        schema || "public",
        mode,
        target,
        mode === "new" ? schemaJsonFromProposal(flow.proposals[0]) : undefined,
        flow.files.map((file) => file.id),
      );
      if (next) setLocalPlan(next);
    } finally {
      setBusy("");
    }
  }

  async function confirmLoad() {
    if (!activePlan) return;
    setBusy("load");
    try {
      await flow.onConfirmLoadPlan(activePlan.id);
      onStep("agent");
    } finally {
      setBusy("");
    }
  }

  return (
    <section className="panel simple-panel">
      <div className="simple-hero">
        <div className="action-icon"><DatabaseZap size={20} /></div>
        <div>
          <span className="workflow-title">{flow.t("tableAndLoad")}</span>
          <h2>{flow.t("chooseWhereSave")}</h2>
          <p>{flow.t("routeAndSchemaAuto")}</p>
        </div>
      </div>
      <DestinationCards mode={mode} setMode={setMode} t={flow.t} />
      <div className="simple-card">
        <strong>{flow.t("aiSuggestedTable")}</strong>
        {mode === "existing" ? (
          <select value={existingKey} onChange={(event) => applyExisting(event.target.value)}>
            <option value="">{flow.t("existingTable")}</option>
            {existingTables.map((item) => <option value={item.key} key={item.key}>{item.label}</option>)}
          </select>
        ) : mode === "new" ? (
          <input value={table} onChange={(event) => setTable(event.target.value)} aria-label={flow.t("targetName")} />
        ) : (
          <p>{flow.t("onlyAgentSearchDetail")}</p>
        )}
        <ColumnChips columns={suggestedColumns(flow.proposals)} />
      </div>
      <details className="simple-details">
        <summary>{flow.t("developerDetails")}</summary>
        <div className="simple-grid-two">
          <label>
            <span>{flow.t("connectionName")}</span>
            <select value={connectionId} onChange={(event) => setConnectionId(event.target.value)}>
              {flow.connections.map((connection) => <option value={connection.id} key={connection.id}>{connection.name}</option>)}
            </select>
          </label>
          <label>
            <span>{flow.t("schemaName")}</span>
            <input value={schema} onChange={(event) => setSchema(event.target.value)} />
          </label>
        </div>
      </details>
      <PreviewSummary plan={activePlan} t={flow.t} onConfirm={confirmLoad} busy={busy} />
      {(!activePlan || activePlan.status === "blocked") && (
        <div className="simple-actions">
          <button disabled={Boolean(busy) || (mode !== "analysis_only" && !table.trim())} onClick={buildPreview} type="button">
            <Eye size={16} />
            <span>{mode === "analysis_only" ? flow.t("createAgentIndex") : flow.t("buildPreview")}</span>
          </button>
        </div>
      )}
    </section>
  );

  function applyExisting(key: string) {
    setExistingKey(key);
    const option = existingTables.find((item) => item.key === key);
    if (!option) return;
    setConnectionId(option.connectionId);
    setSchema(option.schema);
    setTable(option.table);
  }
}

function DestinationCards({ mode, setMode, t }: { mode: DestinationMode; setMode: (mode: DestinationMode) => void; t: SimpleFlowProps["t"] }) {
  return (
    <div className="destination-cards">
      <Choice active={mode === "new"} title={t("newTable")} detail={t("newTableDetail")} onClick={() => setMode("new")} />
      <Choice active={mode === "existing"} title={t("existingTable")} detail={t("existingTableDetail")} onClick={() => setMode("existing")} />
      <Choice active={mode === "analysis_only"} title={t("onlyAgentSearch")} detail={t("onlyAgentSearchDetail")} onClick={() => setMode("analysis_only")} />
    </div>
  );
}

function Choice({ active, title, detail, onClick }: { active: boolean; title: string; detail: string; onClick: () => void }) {
  return <button className={active ? "choice-card active" : "choice-card"} onClick={onClick} type="button"><strong>{title}</strong><small>{detail}</small></button>;
}

function ColumnChips({ columns }: { columns: Array<{ name: string }> }) {
  return <div className="simple-chip-row">{columns.slice(0, 8).map((item) => <span key={item.name}>{item.name}</span>)}</div>;
}

function PreviewSummary({ plan, t, onConfirm, busy }: { plan?: LoadPlan; t: SimpleFlowProps["t"]; onConfirm: () => void; busy: string }) {
  if (!plan) return null;
  const loaded = plan.status === "loaded";
  const blocker = loadBlocker(plan);
  return (
    <div className={loaded ? "simple-success" : "simple-card"}>
      <strong>{loaded ? t("loadComplete") : t("reviewRowsAndLoad")}</strong>
      <span className={`status ${plan.status}`}>{t(plan.status)}</span>
      <div className="simple-metrics">
        <Metric label={t("rows")} value={plan.preview_rows.length} />
        <Metric label={t("validation")} value={plan.validation_issues.length} />
        <Metric label={t("targetTable")} value={`${plan.schema_name}.${plan.target_table}`} />
      </div>
      {blocker && <div className="error-banner">{t(blocker.code)}{blocker.count ? ` · ${blocker.count}` : ""}</div>}
      <details className="simple-details">
        <summary>{t("viewRows")}</summary>
        <PreviewRows rows={plan.preview_rows} />
      </details>
      {!loaded && <button disabled={Boolean(busy) || plan.status !== "needs_confirmation"} onClick={onConfirm}><CheckCircle2 size={16} />{t("loadData")}</button>}
      {loaded && <span><Search size={16} /> {t("dataLoadedReady")}</span>}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="metric"><strong>{value}</strong><span>{label}</span></div>;
}

function PreviewRows({ rows }: { rows: Array<Record<string, unknown>> }) {
  return (
    <div className="simple-row-list">
      {rows.slice(0, 5).map((row, index) => <code key={String(row.row_id ?? index)}>{JSON.stringify(row.field_values ?? row).slice(0, 260)}</code>)}
    </div>
  );
}

function loadBlocker(plan: LoadPlan) {
  return (plan.validation_issues ?? []).find((issue) => issue.severity === "error") as
    | { code: string; count?: number }
    | undefined;
}

async function prepareAiPlan(flow: SimpleFlowProps, mode: DestinationMode) {
  if (flow.datasetId && flow.reviews.some((review) => review.status !== "confirmed")) {
    await api.acceptRecommendedReviews(flow.datasetId);
    await flow.onRefreshReviews();
  }
  const proposal = flow.proposals.find((item) => item.status === "approved") ?? flow.proposals[0];
  if (mode === "new" && proposal && proposal.status !== "approved") {
    await flow.onApproveSchema(proposal.id);
    await flow.onRefreshProposals();
  }
}

function tableOption(table: TableCatalog) {
  return {
    key: `${table.connection_id}:${table.schema_name}:${table.table_name}`,
    connectionId: table.connection_id,
    schema: table.schema_name,
    table: table.table_name,
    label: `${table.schema_name}.${table.table_name} · ${table.description || "catalog"}`,
  };
}
