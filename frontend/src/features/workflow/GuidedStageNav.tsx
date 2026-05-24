import { ArrowLeft, ArrowRight, Bot, DatabaseZap, FileUp, Route, Search, Table2 } from "lucide-react";
import type { WorkflowStage } from "./workflowState";

export type FlowStep = WorkflowStage;

type Tab = {
  id: FlowStep;
  label: string;
};

type Props = {
  tabs: Tab[];
  step: FlowStep;
  selected: boolean;
  onStep: (step: FlowStep) => void;
  t: (key: string) => string;
};

export function GuidedStageNav({ tabs, step, selected, onStep, t }: Props) {
  const index = Math.max(0, tabs.findIndex((tab) => tab.id === step));
  const meta = stageMeta(step, t);
  const Icon = meta.icon;
  return (
    <section className="stage-console">
      <div className="stage-console-head">
        <div className="action-icon"><Icon size={20} /></div>
        <div>
          <span className="workflow-title">{index + 1}/{tabs.length}</span>
          <h2>{meta.title}</h2>
          <p>{meta.detail}</p>
        </div>
      </div>
      <nav className="guided-tabs" aria-label={t("workflow")}>
        {tabs.map((tab, tabIndex) => (
          <button
            aria-current={step === tab.id ? "step" : undefined}
            className={step === tab.id ? "active" : ""}
            data-index={tabIndex + 1}
            onClick={() => onStep(tab.id)}
            type="button"
            key={tab.id}
          >
            {tab.label}
          </button>
        ))}
      </nav>
      <div className="stage-actions">
        <button disabled={index <= 0} onClick={() => onStep(tabs[index - 1].id)} type="button">
          <ArrowLeft size={16} />
          <span>{t("back")}</span>
        </button>
        <button disabled={index >= tabs.length - 1 || !selected} onClick={() => onStep(tabs[index + 1].id)} type="button">
          <span>{t("continue")}</span>
          <ArrowRight size={16} />
        </button>
      </div>
    </section>
  );
}

function stageMeta(step: FlowStep, t: Props["t"]) {
  const meta = {
    upload: ["upload", "actionUploadDetail", FileUp],
    extraction: ["analyze", "actionAnalyzeDetail", Bot],
    summary: ["documentSummary", "routeSummary", Bot],
    routing: ["destination", "actionReviewDetail", Route],
    schema: ["schema", "actionSchemaDetail", Table2],
    preview: ["preview", "loadHint", DatabaseZap],
    materialization: ["loadData", "actionLoadDetail", DatabaseZap],
    retrieval: ["search", "actionSearchDetail", Search],
  } satisfies Record<FlowStep, [string, string, typeof FileUp]>;
  const [title, detail, icon] = meta[step] ?? ["workflow", "nextStep", Table2];
  return { title: t(title), detail: t(detail), icon };
}
