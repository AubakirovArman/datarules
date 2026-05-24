import { CheckCircle2, Circle, Database, DatabaseZap, FileUp, Route, ScanSearch, Search, Table2 } from "lucide-react";
import type { DocumentFile, DocumentReview, Job, LoadPlan, SchemaProposal } from "@shared/types";

type Props = {
  selected: boolean;
  files: DocumentFile[];
  job?: Job;
  reviews: DocumentReview[];
  proposals: SchemaProposal[];
  loadPlans: LoadPlan[];
  t: (key: string) => string;
};

export function FlowStepper({ selected, files, job, reviews, proposals, loadPlans, t }: Props) {
  const loaded = loadPlans.some((plan) => plan.status === "loaded");
  const preview = loadPlans.some((plan) => plan.preview_rows.length > 0);
  const agentReady = loadPlans.some((plan) => Boolean(plan.agent_preparation_json?.ready_for_agent));
  const steps = [
    { key: "stepCreate", done: selected, icon: Database },
    { key: "stepUpload", done: files.length > 0, icon: FileUp },
    { key: "stepAnalyze", done: job?.status === "waiting_review" || job?.status === "completed", icon: ScanSearch },
    { key: "stepRoute", done: reviews.length > 0 && reviews.every((review) => review.status === "confirmed"), icon: Route },
    { key: "stepSchema", done: proposals.length > 0, icon: Table2 },
    { key: "stepApprove", done: proposals.some((proposal) => proposal.status === "approved"), icon: CheckCircle2 },
    { key: "stepPreview", done: preview, icon: Table2 },
    { key: "stepLoad", done: loaded, icon: DatabaseZap },
    { key: "stepAgent", done: agentReady, icon: Search },
  ];

  return (
    <section className="workflow-strip">
      <div className="workflow-title">{t("workflow")}</div>
      <div className="steps">
        {steps.map((step, index) => {
          const Icon = step.icon;
          return (
            <div className={step.done ? "step done" : "step"} key={step.key}>
              {step.done ? <CheckCircle2 size={17} /> : <Circle size={17} />}
              <Icon size={17} />
              <span>{t(step.key)}</span>
              {index < steps.length - 1 && <i />}
            </div>
          );
        })}
      </div>
    </section>
  );
}
