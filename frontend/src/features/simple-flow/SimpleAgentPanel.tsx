import { MessageSquare, Search } from "lucide-react";
import { SearchPane } from "@features/search/SearchPane";
import type { SimpleFlowProps } from "./types";
import { latestPlan, planReadyForAgent } from "./simpleFlowState";

type Props = {
  flow: SimpleFlowProps;
};

export function SimpleAgentPanel({ flow }: Props) {
  const plan = latestPlan(flow.loadPlans);
  const ready = planReadyForAgent(plan);
  const questions = [flow.t("questionCount"), flow.t("questionTotal"), flow.t("questionDeadline")];
  return (
    <section className="simple-agent">
      <div className={ready ? "simple-success" : "simple-card"}>
        <strong><MessageSquare size={16} /> {ready ? flow.t("dataLoadedReady") : flow.t("agentNotReady")}</strong>
        {plan && (
          <div className="simple-metrics">
            <Metric label={flow.t("rows")} value={plan.preview_rows.length} />
            <Metric label={flow.t("targetTable")} value={`${plan.schema_name}.${plan.target_table}`} />
            <Metric label={flow.t("searchModes")} value={searchModes(plan)} />
          </div>
        )}
        <div className="simple-chip-row">
          {questions.map((question) => <span key={question}><Search size={13} /> {question}</span>)}
        </div>
      </div>
      <SearchPane
        datasetId={flow.datasetId}
        disabled={flow.disabled || !ready}
        onSearch={flow.onSearch}
        onAsk={flow.onAsk}
        simple
        suggestions={questions}
        t={flow.t}
      />
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return <div className="metric"><strong>{value}</strong><span>{label}</span></div>;
}

function searchModes(plan: ReturnType<typeof latestPlan>) {
  const readiness = plan?.agent_preparation_json ?? {};
  const modes = ["keyword", "BM25", "vector"];
  if (readiness.analysis_only) modes.unshift("docs");
  return modes.join(" + ");
}
