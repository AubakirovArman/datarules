import { Bot, DatabaseZap, FileUp, PlayCircle, Route, Search, Table2 } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@shared/api";
import type { DatasetReadiness, DocumentFile, DocumentReview, DocumentSummary, Job, LoadPlan, ReadinessAction, SchemaProposal } from "@shared/types";

type Step = "upload" | "analyze" | "summary" | "destination" | "load" | "search";

type Props = {
  selected: boolean;
  files: DocumentFile[];
  job?: Job;
  summaries: DocumentSummary[];
  reviews: DocumentReview[];
  proposals: SchemaProposal[];
  loadPlans: LoadPlan[];
  datasetId?: string;
  refreshKey: string;
  onStart: () => Promise<Job | undefined>;
  onNavigate: (step: Step, action?: ReadinessAction) => void;
  t: (key: string) => string;
};

type Action = {
  title: string;
  detail: string;
  button: string;
  step: Step;
  run?: () => Promise<void>;
  icon: typeof FileUp;
  disabled?: boolean;
  source?: ReadinessAction;
};

export function WorkflowActionCenter(props: Props) {
  const [readiness, setReadiness] = useState<DatasetReadiness>();
  useEffect(() => {
    if (!props.datasetId) {
      setReadiness(undefined);
      return;
    }
    api.readiness(props.datasetId).then(setReadiness).catch(() => setReadiness(undefined));
  }, [props.datasetId, props.refreshKey]);
  const action = readinessAction(props, readiness) ?? nextAction(props);
  const Icon = action.icon;
  const stats = workflowStats(props, readiness);
  return (
    <section className="workflow-action">
      <div className="workflow-action-main">
        <div className="action-icon"><Icon size={20} /></div>
        <div>
          <span className="workflow-title">{props.t("actionCenter")}</span>
          <strong>{action.title}</strong>
          <small>{action.detail}</small>
        </div>
      </div>
      <div className="workflow-action-stats">
        {stats.map((item) => (
          <span className={item.ready ? "ready" : ""} key={item.key}>
            <strong>{item.value}</strong>
            {props.t(item.key)}
          </span>
        ))}
      </div>
      <button
        disabled={action.disabled}
        onClick={() => void runAction(action, props.onNavigate)}
        type="button"
      >
        <PlayCircle size={16} />
        <span>{action.button}</span>
      </button>
    </section>
  );
}

function readinessAction(props: Props, readiness?: DatasetReadiness): Action | undefined {
  const item = readiness?.action_plan?.[0];
  if (!item) return undefined;
  return {
    ...action(
      props,
      item.title_key,
      item.detail_key,
      item.cta_key,
      stepValue(item.step),
      iconForAction(item),
      item.code === "wait_for_summary",
      item.code === "run_extraction" ? props.onStart : undefined,
    ),
    source: item,
  };
}

function nextAction(props: Props): Action {
  const running = props.job?.status === "running" || props.job?.status === "queued";
  const analyzed = props.summaries.length > 0 || ["waiting_review", "completed"].includes(props.job?.status ?? "");
  const confirmedRoutes = props.reviews.length > 0 && props.reviews.every((review) => review.status === "confirmed");
  const approvedSchema = props.proposals.some((proposal) => proposal.status === "approved");
  const latestPlan = props.loadPlans[0];
  const loaded = props.loadPlans.some((plan) => plan.status === "loaded");
  const agentReady = props.loadPlans.some((plan) => Boolean(plan.agent_preparation_json?.ready_for_agent));
  if (!props.files.length) return action(props, "actionUpload", "actionUploadDetail", "actionButtonUpload", "upload", FileUp);
  if (running) return action(props, "actionAnalyzing", "actionAnalyzingDetail", "actionButtonAnalyzing", "analyze", Bot, true);
  if (!analyzed) return action(props, "actionAnalyze", "actionAnalyzeDetail", "actionButtonAnalyze", "analyze", Bot, false, props.onStart);
  if (!confirmedRoutes) return action(props, "actionReview", "actionReviewDetail", "actionButtonReview", "destination", Route);
  if (!approvedSchema) return action(props, "actionSchema", "actionSchemaDetail", "actionButtonSchema", "destination", Table2);
  if (!latestPlan || latestPlan.status !== "loaded") {
    return action(props, "actionLoad", "actionLoadDetail", "actionButtonLoad", "load", DatabaseZap);
  }
  if (loaded && !agentReady) return action(props, "actionIndex", "actionIndexDetail", "actionButtonIndex", "load", DatabaseZap);
  return action(props, "actionSearch", "actionSearchDetail", "actionButtonSearch", "search", Search);
}

function action(
  props: Props,
  title: string,
  detail: string,
  button: string,
  step: Step,
  icon: Action["icon"],
  disabled = false,
  run?: () => Promise<Job | undefined>,
): Action {
  return {
    title: props.t(title),
    detail: props.t(detail),
    button: props.t(button),
    step,
    icon,
    disabled: disabled || (step !== "upload" && !props.selected),
    run: run ? async () => { await run(); } : undefined,
  };
}

async function runAction(action: Action, navigate: Props["onNavigate"]) {
  if (action.run) {
    await action.run();
  }
  navigate(action.step, action.source);
}

function stepValue(value: string): Step {
  return ["upload", "analyze", "summary", "destination", "load", "search"].includes(value) ? value as Step : "upload";
}

function iconForAction(item: ReadinessAction) {
  if (item.step === "upload") return FileUp;
  if (item.step === "analyze" || item.code === "wait_for_summary") return Bot;
  if (item.step === "destination" && item.code.includes("schema")) return Table2;
  if (item.step === "destination") return Route;
  if (item.step === "load") return DatabaseZap;
  return Search;
}

function workflowStats(props: Props, readiness?: DatasetReadiness) {
  if (readiness) return readinessStats(readiness);
  const confirmed = props.reviews.filter((review) => review.status === "confirmed").length;
  const latestPlan = props.loadPlans[0];
  return [
    { key: "files", value: props.files.length, ready: props.files.length > 0 },
    { key: "gemmaSummary", value: props.summaries.length, ready: props.summaries.length > 0 },
    { key: "documentRouting", value: `${confirmed}/${props.reviews.length}`, ready: props.reviews.length > 0 && confirmed === props.reviews.length },
    { key: "schema", value: props.proposals.filter((proposal) => proposal.status === "approved").length, ready: props.proposals.some((proposal) => proposal.status === "approved") },
    { key: "preview", value: latestPlan?.preview_rows.length ?? 0, ready: Boolean(latestPlan?.preview_rows.length) },
    { key: "agentTables", value: props.loadPlans.filter((plan) => plan.status === "loaded").length, ready: props.loadPlans.some((plan) => plan.status === "loaded") },
  ];
}

function readinessStats(readiness: DatasetReadiness) {
  const counts = readiness.counts;
  return [
    { key: "files", value: counts.documents ?? 0, ready: stageReady(readiness, "upload") },
    { key: "gemmaSummary", value: counts.ai_summaries ?? 0, ready: stageReady(readiness, "summary") },
    { key: "documentRouting", value: `${counts.reviews_confirmed ?? 0}/${counts.reviews ?? 0}`, ready: stageReady(readiness, "routing") },
    { key: "schema", value: counts.schema_approved ?? 0, ready: stageReady(readiness, "schema") },
    { key: "preview", value: stageCount(readiness, "preview"), ready: stageReady(readiness, "preview") },
    { key: "agentTables", value: readiness.agent.loaded_plans, ready: readiness.agent.ready },
  ];
}

function stageReady(readiness: DatasetReadiness, key: string) {
  return readiness.stages.find((stage) => stage.key === key)?.status === "ready";
}

function stageCount(readiness: DatasetReadiness, key: string) {
  return readiness.stages.find((stage) => stage.key === key)?.count ?? 0;
}
