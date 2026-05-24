import type { DatasetReadiness, ReadinessAction } from "@shared/types";

export type WorkflowStage =
  | "upload"
  | "extraction"
  | "summary"
  | "routing"
  | "schema"
  | "preview"
  | "materialization"
  | "retrieval";

export const workflowStages: WorkflowStage[] = [
  "upload",
  "extraction",
  "summary",
  "routing",
  "schema",
  "preview",
  "materialization",
  "retrieval",
];

export type WorkflowView = {
  currentStage: WorkflowStage;
  currentIndex: number;
  nextActionCode: string;
  blockedBy: string[];
  canContinue: boolean;
  action?: ReadinessAction;
};

export function deriveWorkflowView(readiness?: DatasetReadiness): WorkflowView {
  const action = readiness?.action_plan?.[0];
  const fromAction = action ? stageFromAction(action) : undefined;
  const fromStage = readiness?.stages.find((stage) => stage.status !== "ready")?.key;
  const currentStage = fromAction ?? normalizeStage(fromStage);
  return {
    currentStage,
    currentIndex: workflowStages.indexOf(currentStage),
    nextActionCode: action?.code ?? "ready_for_agent",
    blockedBy: readiness?.next_actions ?? [],
    canContinue: Boolean(action),
    action,
  };
}

export function stageFromAction(action?: Pick<ReadinessAction, "step" | "code">): WorkflowStage {
  const code = action?.code ?? "";
  if (code === "run_extraction" || code === "wait_for_summary") return "extraction";
  if (code.includes("routing") || code.includes("review")) return "routing";
  if (code.includes("schema")) return "schema";
  if (code.includes("preview") || code.includes("fix_preview")) return "preview";
  if (code.includes("load") || code.includes("material")) return "materialization";
  if (code.includes("index") || code.includes("retrieval") || code.includes("agent")) return "retrieval";
  return normalizeStage(action?.step);
}

export function normalizeStage(value?: string): WorkflowStage {
  if (!value) return "upload";
  if (workflowStages.includes(value as WorkflowStage)) return value as WorkflowStage;
  const legacy: Record<string, WorkflowStage> = {
    analyze: "extraction",
    destination: "routing",
    load: "preview",
    search: "retrieval",
  };
  return legacy[value] ?? "upload";
}
