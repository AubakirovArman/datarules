import { Bot, DatabaseZap, FileUp, MessageSquare } from "lucide-react";
import type { SimpleStep, SimpleFlowProps } from "./types";
import { stepUnlocked } from "./simpleFlowState";

type Props = {
  step: SimpleStep;
  flow: SimpleFlowProps;
  onStep: (step: SimpleStep) => void;
};

const steps: Array<{ id: SimpleStep; key: string; icon: typeof FileUp }> = [
  { id: "documents", key: "simpleStepDocuments", icon: FileUp },
  { id: "analysis", key: "simpleStepAnalysis", icon: Bot },
  { id: "destination", key: "simpleStepDestination", icon: DatabaseZap },
  { id: "agent", key: "simpleStepAgent", icon: MessageSquare },
];

export function SimpleStepper({ step, flow, onStep }: Props) {
  return (
    <nav className="simple-stepper" aria-label={flow.t("workflow")}>
      {steps.map((item, index) => {
        const Icon = item.icon;
        const unlocked = stepUnlocked(item.id, flow);
        return (
          <button
            aria-current={step === item.id ? "step" : undefined}
            className={step === item.id ? "active" : ""}
            disabled={!unlocked}
            onClick={() => onStep(item.id)}
            type="button"
            key={item.id}
          >
            <span>{index + 1}</span>
            <Icon size={16} />
            <strong>{flow.t(item.key)}</strong>
          </button>
        );
      })}
    </nav>
  );
}
