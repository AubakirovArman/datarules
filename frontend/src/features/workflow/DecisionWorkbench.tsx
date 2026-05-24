import { Bot, CheckCircle2, DatabaseZap, FileUp, Route, Search, Table2 } from "lucide-react";
import { useState } from "react";
import { api } from "@shared/api";
import type { DocumentFile, DocumentReview, DocumentSummary, LoadPlan, SchemaProposal } from "@shared/types";
import type { WorkflowStage } from "./workflowState";

type Step = WorkflowStage;

type Props = {
  datasetId?: string;
  files: DocumentFile[];
  summaries: DocumentSummary[];
  reviews: DocumentReview[];
  proposals: SchemaProposal[];
  loadPlans: LoadPlan[];
  onNavigate: (step: Step) => void;
  onRefreshReviews: () => Promise<void>;
  onApproveSchema: (id: string) => Promise<void>;
  t: (key: string) => string;
};

export function DecisionWorkbench(props: Props) {
  const [busy, setBusy] = useState("");
  const state = decisionState(props);
  const stages = stageRows(props);
  const ActionIcon = state.icon;
  return (
    <section className="decision-workbench">
      <div className="decision-head">
        <div>
          <span className="workflow-title">{props.t("decisionWorkbench")}</span>
          <strong>{props.t(state.title)}</strong>
          <small>{props.t(state.detail)}</small>
        </div>
        <button disabled={Boolean(busy)} onClick={() => void runAction(state, props, setBusy)} type="button">
          <ActionIcon size={16} />
          <span>{props.t(state.button)}</span>
        </button>
      </div>
      <div className="decision-grid">
        {stages.map((stage) => <StageButton stage={stage} onNavigate={props.onNavigate} t={props.t} key={stage.key} />)}
      </div>
    </section>
  );
}

function StageButton({ stage, onNavigate, t }: { stage: StageRow; onNavigate: Props["onNavigate"]; t: Props["t"] }) {
  const Icon = stage.icon;
  return (
    <button
      className={stage.ready ? "ready" : stage.active ? "active" : ""}
      onClick={() => onNavigate(stage.step)}
      type="button"
    >
      {stage.ready ? <CheckCircle2 size={16} /> : <Icon size={16} />}
      <span>{t(stage.key)}</span>
      <small>{stage.detail}</small>
    </button>
  );
}

function decisionState(props: Props) {
  const pendingRoutes = props.reviews.filter((review) => review.status !== "confirmed");
  const approvedSchema = props.proposals.find((proposal) => proposal.status === "approved");
  const latestPlan = props.loadPlans[0];
  const agentReady = props.loadPlans.some((plan) => Boolean(plan.agent_preparation_json?.ready_for_agent));
  if (!props.files.length) return row("decisionOpenUpload", "decisionUploadBlocked", "decisionOpenUpload", "upload", FileUp);
  if (!props.summaries.length) return row("decisionOpenAnalyze", "decisionAnalysisBlocked", "decisionOpenAnalyze", "extraction", Bot);
  if (pendingRoutes.length) {
    return row("decisionAcceptRoutes", "decisionRouteBlocked", "decisionAcceptRoutes", "routing", Route, "accept");
  }
  if (!approvedSchema) {
    const action = props.proposals.length ? "approve_schema" : undefined;
    return row("decisionApproveSchema", "decisionSchemaBlocked", "decisionApproveSchema", "schema", Table2, action);
  }
  if (!latestPlan || latestPlan.status !== "loaded") {
    return row("decisionOpenLoad", "decisionLoadBlocked", "decisionOpenLoad", "preview", DatabaseZap);
  }
  if (!agentReady) return row("decisionOpenLoad", "decisionIndexBlocked", "decisionOpenLoad", "retrieval", DatabaseZap);
  return row("decisionOpenSearch", "decisionReady", "decisionOpenSearch", "retrieval", Search);
}

function row(
  title: string,
  detail: string,
  button: string,
  step: Step,
  icon: typeof FileUp,
  action?: "accept" | "approve_schema",
) {
  return { title, detail, button, step, icon, action };
}

async function runAction(state: ReturnType<typeof decisionState>, props: Props, setBusy: (value: string) => void) {
  if (state.action === "accept" && props.datasetId) {
    setBusy("accept");
    try {
      await api.acceptRecommendedReviews(props.datasetId);
      await props.onRefreshReviews();
    } finally {
      setBusy("");
    }
  } else if (state.action === "approve_schema") {
    const proposal = props.proposals.find((item) => item.status !== "approved") ?? props.proposals[0];
    if (proposal) {
      setBusy("schema");
      try {
        await props.onApproveSchema(proposal.id);
      } finally {
        setBusy("");
      }
    }
  }
  props.onNavigate(state.step);
}

function stageRows(props: Props) {
  const confirmed = props.reviews.filter((review) => review.status === "confirmed").length;
  const plan = props.loadPlans[0];
  return [
    stage("decisionStepAnalysis", "summary", props.summaries.length > 0, `${props.summaries.length}/${props.files.length}`, Bot),
    stage("decisionStepRouting", "routing", props.reviews.length > 0 && confirmed === props.reviews.length, `${confirmed}/${props.reviews.length}`, Route),
    stage("decisionStepSchema", "schema", props.proposals.some((item) => item.status === "approved"), String(props.proposals.length), Table2),
    stage("decisionStepLoad", "materialization", Boolean(plan?.status === "loaded"), plan?.status ?? "pending", DatabaseZap),
    stage("decisionStepAgent", "retrieval", props.loadPlans.some((item) => Boolean(item.agent_preparation_json?.ready_for_agent)), props.loadPlans.length ? "agent" : "pending", Search),
  ];
}

type StageRow = ReturnType<typeof stage>;

function stage(key: string, step: Step, ready: boolean, detail: string, icon: typeof FileUp) {
  return { key, step, ready, active: !ready, detail, icon };
}
