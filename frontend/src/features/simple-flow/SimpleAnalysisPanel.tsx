import { ArrowLeft, Bot, CheckCircle2, DatabaseZap, PlayCircle } from "lucide-react";
import { useState } from "react";
import { JobProgress } from "@features/workflow/JobProgress";
import type { SimpleFlowProps, SimpleStep } from "./types";
import { analysisStats, latestPlan, suggestedColumns, suggestedTable } from "./simpleFlowState";

type Props = {
  flow: SimpleFlowProps;
  onStep: (step: SimpleStep) => void;
};

export function SimpleAnalysisPanel({ flow, onStep }: Props) {
  const [busy, setBusy] = useState(false);
  const running = ["queued", "running", "cancelling"].includes(flow.job?.status ?? "");
  if (running) {
    return <JobProgress job={flow.job} events={flow.events} t={flow.t} />;
  }
  if (flow.summaries.length === 0) {
    return (
      <section className="panel simple-panel">
        <div className="simple-hero">
          <div className="action-icon"><Bot size={20} /></div>
          <div>
            <span className="workflow-title">{flow.t("simpleStepAnalysis")}</span>
            <h2>{flow.t("actionAnalyze")}</h2>
            <p>{flow.t("actionAnalyzeDetail")}</p>
          </div>
        </div>
        <div className="simple-actions">
          <button disabled={busy || flow.files.length === 0} onClick={() => void start()} type="button">
            <PlayCircle size={16} />
            <span>{flow.t("actionButtonAnalyze")}</span>
          </button>
        </div>
      </section>
    );
  }
  const stats = analysisStats(flow.summaries, latestPlan(flow.loadPlans));
  const columns = suggestedColumns(flow.proposals);
  const summary = flow.summaries[0];
  return (
    <section className="panel simple-panel">
      <div className="simple-hero">
        <div className="action-icon"><Bot size={20} /></div>
        <div>
          <span className="workflow-title">{flow.t("analysisReady")}</span>
          <h2>{flow.t("aiUnderstoodDocuments")}</h2>
          <p>{String(summary.ai_summary?.summary ?? summary.summary)}</p>
        </div>
      </div>
      <div className="simple-metrics">
        <Metric label={flow.t("documents")} value={stats.documents || flow.files.length} />
        <Metric label={flow.t("pages")} value={stats.pages} />
        <Metric label={flow.t("tables")} value={stats.tables} />
        <Metric label={flow.t("rowsFound")} value={stats.rows || "-"} />
      </div>
      <div className="simple-card">
        <strong><DatabaseZap size={16} /> {flow.t("aiSuggestedTable")}</strong>
        <h3>{suggestedTable(flow.proposals)}</h3>
        <p>{flow.t("aiSuggestedTableDetail")}</p>
        <div className="simple-chip-row">
          {columns.slice(0, 8).map((column) => <span key={column.name}>{column.name}</span>)}
          {columns.length === 0 && <span>project_name</span>}
        </div>
      </div>
      <div className="simple-actions">
        <button onClick={() => onStep("destination")} type="button">
          <CheckCircle2 size={16} />
          <span>{flow.t("chooseWhereSave")}</span>
        </button>
        <button className="ghost-button" onClick={() => onStep("documents")} type="button">
          <ArrowLeft size={16} />
          <span>{flow.t("back")}</span>
        </button>
      </div>
    </section>
  );

  async function start() {
    setBusy(true);
    try {
      await flow.onStart();
    } finally {
      setBusy(false);
    }
  }
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
