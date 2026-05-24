import { Settings } from "lucide-react";
import { useEffect, useState } from "react";
import { UploadPane } from "@features/upload/UploadPane";
import { GuidedFlow } from "@features/workflow/GuidedFlow";
import { deriveSimpleStep } from "./simpleFlowState";
import { SimpleAgentPanel } from "./SimpleAgentPanel";
import { SimpleAnalysisPanel } from "./SimpleAnalysisPanel";
import { SimpleDestinationPanel } from "./SimpleDestinationPanel";
import { SimpleStepper } from "./SimpleStepper";
import type { SimpleFlowProps, SimpleStep } from "./types";

export function SimpleFlow(props: SimpleFlowProps) {
  const suggestedStep = deriveSimpleStep(props);
  const [step, setStep] = useState<SimpleStep>(suggestedStep);
  const [advanced, setAdvanced] = useState(false);

  useEffect(() => {
    setStep(suggestedStep);
  }, [suggestedStep]);

  if (advanced) {
    return (
      <div className="simple-flow">
        <div className="simple-topline">
          <button className="ghost-button" onClick={() => setAdvanced(false)} type="button">{props.t("simpleMode")}</button>
        </div>
        <GuidedFlow {...props} />
      </div>
    );
  }

  return (
    <div className="simple-flow">
      <div className="simple-topline">
        <div>
          <span className="workflow-title">{props.t("simpleFlow")}</span>
          <h1>{props.t("simpleFlowTitle")}</h1>
        </div>
        <button className="ghost-button" onClick={() => setAdvanced(true)} type="button">
          <Settings size={16} />
          <span>{props.t("advancedWorkflow")}</span>
        </button>
      </div>
      <SimpleStepper step={step} flow={props} onStep={setStep} />
      <div className="simple-stage">
        {step === "documents" && (
          <UploadPane
            disabled={false}
            files={props.files}
            onUpload={props.onUpload}
            onDelete={props.onDelete}
            onRefresh={props.onRefreshFiles}
            onStart={props.onStart}
            t={props.t}
          />
        )}
        {step === "analysis" && <SimpleAnalysisPanel flow={props} onStep={setStep} />}
        {step === "destination" && <SimpleDestinationPanel flow={props} onStep={setStep} />}
        {step === "agent" && <SimpleAgentPanel flow={props} />}
      </div>
    </div>
  );
}
