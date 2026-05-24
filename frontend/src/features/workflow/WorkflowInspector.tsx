import type {
  DocumentFile,
  DocumentReview,
  DocumentSummary,
  LoadPlan,
  ReadinessAction,
  SchemaProposal,
} from "@shared/types";
import { DatasetReport } from "@features/reporting/DatasetReport";
import { DecisionWorkbench } from "./DecisionWorkbench";
import { ReadinessPanel } from "./ReadinessPanel";

type Props = {
  datasetId?: string;
  files: DocumentFile[];
  summaries: DocumentSummary[];
  reviews: DocumentReview[];
  proposals: SchemaProposal[];
  loadPlans: LoadPlan[];
  refreshKey: string;
  onNavigate: (step: string, action?: ReadinessAction) => void;
  onRefreshReviews: () => Promise<void>;
  onApproveSchema: (id: string) => Promise<void>;
  t: (key: string) => string;
};

export function WorkflowInspector(props: Props) {
  return (
    <details className="workflow-inspector">
      <summary>
        <span className="workflow-title">{props.t("readiness")}</span>
        <strong>{props.t("decisionWorkbench")}</strong>
        <small>{props.t("verificationReport")}</small>
      </summary>
      <div className="inspector-stack">
        <ReadinessPanel
          datasetId={props.datasetId}
          refreshKey={props.refreshKey}
          onNavigate={props.onNavigate}
          t={props.t}
        />
        <DecisionWorkbench
          datasetId={props.datasetId}
          files={props.files}
          summaries={props.summaries}
          reviews={props.reviews}
          proposals={props.proposals}
          loadPlans={props.loadPlans}
          onNavigate={props.onNavigate}
          onRefreshReviews={props.onRefreshReviews}
          onApproveSchema={props.onApproveSchema}
          t={props.t}
        />
        <DatasetReport datasetId={props.datasetId} refreshKey={props.refreshKey} t={props.t} />
      </div>
    </details>
  );
}
