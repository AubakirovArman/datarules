import type { DocumentSummary, LoadPlan, SchemaProposal } from "@shared/types";
import { isDataRulesManagedColumn } from "@shared/managedColumns";
import type { SimpleFlowProps, SimpleStep } from "./types";

export type DestinationMode = "new" | "existing" | "analysis_only";

export function deriveSimpleStep(props: SimpleFlowProps): SimpleStep {
  const running = ["queued", "running", "cancelling"].includes(props.job?.status ?? "");
  const loaded = props.loadPlans.some((plan) => plan.status === "loaded");
  if (!props.files.length) return "documents";
  if (running || !props.summaries.length) return "analysis";
  if (loaded) return "agent";
  return "destination";
}

export function stepUnlocked(step: SimpleStep, props: SimpleFlowProps) {
  if (step === "documents") return true;
  if (step === "analysis") return props.files.length > 0;
  if (step === "destination") return props.summaries.length > 0;
  return props.loadPlans.some((plan) => plan.status === "loaded" || Boolean(plan.agent_preparation_json?.ready_for_agent));
}

export function analysisStats(summaries: DocumentSummary[], plan?: LoadPlan) {
  return {
    documents: summaries.length,
    pages: summaries.reduce((sum, item) => sum + item.pages, 0),
    tables: summaries.reduce((sum, item) => sum + item.tables, 0),
    rows: plan?.preview_rows.length ?? 0,
  };
}

export function firstTable(proposal?: SchemaProposal) {
  const tables = Array.isArray(proposal?.proposal_json.tables) ? proposal?.proposal_json.tables : [];
  return objectValue(tables[0]);
}

export function suggestedTable(proposals: SchemaProposal[]) {
  const table = firstTable(proposals[0]);
  return String(table.name ?? table.table_name ?? "investment_projects");
}

export function suggestedColumns(proposals: SchemaProposal[]) {
  const table = firstTable(proposals[0]);
  const columns = Array.isArray(table.columns) ? table.columns : [];
  return columns
    .map(objectValue)
    .map((item) => ({
      name: String(item.name ?? "field"),
      type: String(item.type ?? "text"),
      required: Boolean(item.required),
    }))
    .filter((item) => item.name && !isDataRulesManagedColumn(item.name));
}

export function schemaJsonFromProposal(proposal?: SchemaProposal) {
  const table = firstTable(proposal);
  const columns = suggestedColumns(proposal ? [proposal] : []);
  return {
    schema_source: "user_supplied_schema",
    description: String(table.purpose ?? proposal?.proposal_json.dataset_summary ?? ""),
    target_columns: columns,
    source_references_required: true,
  };
}

export function latestPlan(plans: LoadPlan[]) {
  return plans[0];
}

export function planReadyForAgent(plan?: LoadPlan) {
  return Boolean(plan?.agent_preparation_json?.ready_for_agent) || plan?.status === "loaded";
}

export function planMatches(plan: LoadPlan | undefined, mode: DestinationMode, schema: string, table: string) {
  if (!plan) return false;
  const target = mode === "analysis_only" ? "analysis_only" : table.trim();
  return plan.target_mode === mode && plan.schema_name === schema && plan.target_table === target;
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
