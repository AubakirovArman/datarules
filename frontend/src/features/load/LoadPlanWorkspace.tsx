import type { LoadPlan } from "@shared/types";
import { AgentReadinessReport } from "./AgentReadinessReport";
import { LoadedRowsBrowser } from "./LoadedRowsBrowser";
import { LoadIssues } from "./LoadIssues";
import { LoadPlanActions } from "./LoadPlanActions";
import { LoadPlanTimeline } from "./LoadPlanTimeline";
import { LoadQuarantinePanel } from "./LoadQuarantinePanel";
import { LoadReport } from "./LoadReport";
import { PreviewEditor } from "./PreviewEditor";
import { useState } from "react";

export type LoadPaneView = "preview" | "materialization";

type Props = {
  plan: LoadPlan;
  preflightBlocked: boolean;
  view: LoadPaneView;
  onUpdateRows: (planId: string, rows: LoadPlan["preview_rows"]) => Promise<void>;
  onConfirm: (planId: string) => Promise<void>;
  onPlanUpdated: (plan: LoadPlan) => void;
  t: (key: string) => string;
};

export function LoadPlanWorkspace({
  plan,
  preflightBlocked,
  view,
  onUpdateRows,
  onConfirm,
  onPlanUpdated,
  t,
}: Props) {
  const [dirty, setDirty] = useState(false);
  const isMaterialization = view === "materialization";
  return (
    <div className={`load-preview load-preview-${view}`}>
      <div className="load-status">
        <h3>{plan.schema_name}.{plan.target_table}</h3>
        <span className={`status ${plan.status}`}>{t(plan.status)}</span>
        <small>{plan.preview_rows.length} {t("rows")}</small>
      </div>
      {isMaterialization && <AgentReadinessReport value={plan.agent_preparation_json} t={t} />}
      {isMaterialization && <LoadReport planId={plan.id} refreshKey={plan.updated_at} t={t} />}
      {isMaterialization && (
        <LoadedRowsBrowser
          planId={plan.id}
          enabled={plan.status === "loaded" && plan.target_mode !== "analysis_only"}
          refreshKey={plan.updated_at}
          t={t}
        />
      )}
      <LoadIssues issues={plan.validation_issues} t={t} />
      {isMaterialization && <LoadQuarantinePanel planId={plan.id} refreshKey={plan.updated_at} t={t} />}
      {isMaterialization && <LoadPlanTimeline events={plan.events} />}
      <PreviewEditor plan={plan} onSave={(rows) => onUpdateRows(plan.id, rows)} onDirtyChange={setDirty} t={t} />
      {dirty && <small className="load-save-warning">{t("savePreviewBeforeLoad")}</small>}
      {isMaterialization && (
        <LoadPlanActions
          plan={plan}
          preflightBlocked={preflightBlocked}
          dirty={dirty}
          onConfirm={onConfirm}
          onPlanUpdated={onPlanUpdated}
          t={t}
        />
      )}
    </div>
  );
}
