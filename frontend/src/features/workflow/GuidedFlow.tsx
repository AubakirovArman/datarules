import { useEffect, useState } from "react";
import type {
  DbConnection,
  DocumentFile,
  DocumentReview,
  DocumentSummary,
  Job,
  JobEvent,
  LoadPlan,
  AskResponse,
  SearchHit,
  SchemaChatResponse,
  SchemaProposal,
  TableCatalog,
  ReadinessAction,
} from "@shared/types";
import { GuidedStageNav, type FlowStep } from "./GuidedStageNav";
import { JobProgress } from "./JobProgress";
import { LoadPane } from "@features/load/LoadPane";
import { ReviewPane } from "@features/routing/ReviewPane";
import { SearchPane } from "@features/search/SearchPane";
import { SchemaChatPane } from "@features/schema/SchemaChatPane";
import { SchemaPane } from "@features/schema/SchemaPane";
import { SummaryPane } from "@features/summary/SummaryPane";
import { UploadPane } from "@features/upload/UploadPane";
import { WorkflowActionCenter } from "./WorkflowActionCenter";
import { WorkflowInspector } from "./WorkflowInspector";

type Props = {
  selected: boolean;
  files: DocumentFile[];
  job?: Job;
  events: JobEvent[];
  summaries: DocumentSummary[];
  reviews: DocumentReview[];
  proposals: SchemaProposal[];
  loadPlans: LoadPlan[];
  connections: DbConnection[];
  tables: TableCatalog[];
  datasetId?: string;
  disabled: boolean;
  onUpload: (files: FileList) => Promise<void>;
  onDelete: (documentId: string) => Promise<void>;
  onStart: () => Promise<Job | undefined>;
  onRefreshFiles: () => Promise<void>;
  onRefreshSummaries: () => Promise<void>;
  onRefreshReviews: () => Promise<void>;
  onConfirmReview: (id: string, docType: string, table: string, notes: string) => Promise<void>;
  onRefreshProposals: () => Promise<void>;
  onApproveSchema: (id: string) => Promise<void>;
  onSchemaChat: (message: string) => Promise<SchemaChatResponse>;
  onCreateLoadPlan: (
    connectionId: string | undefined,
    schema: string,
    mode: string,
    table: string,
    schemaJson?: Record<string, unknown>,
    documentIds?: string[],
    schemaVersionId?: string,
  ) => Promise<LoadPlan | undefined>;
  onUpdateLoadPlanRows: (planId: string, rows: LoadPlan["preview_rows"]) => Promise<void>;
  onConfirmLoadPlan: (planId: string) => Promise<void>;
  onSearch: (query: string) => Promise<SearchHit[]>;
  onAsk: (query: string) => Promise<AskResponse>;
  t: (key: string) => string;
};

type Step = FlowStep;

export function GuidedFlow(props: Props) {
  const [step, setStep] = useState<Step>("upload");
  const [focusCode, setFocusCode] = useState("");
  const tabs: Array<{ id: Step; label: string }> = [
    { id: "upload", label: props.t("upload") },
    { id: "analyze", label: props.t("analyze") },
    { id: "summary", label: props.t("documentSummary") },
    { id: "destination", label: props.t("destination") },
    { id: "load", label: props.t("previewLoad") },
    { id: "search", label: props.t("search") },
  ];
  const readinessKey = [
    props.files.length,
    props.job?.status,
    props.summaries.length,
    props.reviews.filter((review) => review.status === "confirmed").length,
    props.proposals.map((proposal) => `${proposal.id}:${proposal.status}`).join("|"),
    props.loadPlans[0]?.status,
    props.loadPlans[0]?.updated_at,
  ].join(":");

  useEffect(() => {
    if (step === "analyze" && ["waiting_review", "completed"].includes(props.job?.status ?? "")) {
      setStep("summary");
    }
  }, [props.job?.status, step]);

  async function startAnalysis() {
    const nextJob = await props.onStart();
    if (nextJob) {
      setStep("analyze");
    }
    return nextJob;
  }

  function useChatProposal(proposal: Record<string, unknown>) {
    const connection = props.connections.find((item) => item.is_internal) ?? props.connections[0];
    const table = safeTableName(String(proposal.table_name ?? "custom_records"));
    return props.onCreateLoadPlan(
      connection?.id,
      connection?.default_schema ?? "public",
      "new",
      table,
      schemaFromProposal(proposal),
      props.files.map((file) => file.id),
    );
  }

  const handleReadinessNavigate = handleReadinessNavigateFactory(setStep, setFocusCode);

  return (
    <>
      <WorkflowActionCenter
        selected={props.selected}
        files={props.files}
        job={props.job}
        summaries={props.summaries}
        reviews={props.reviews}
        proposals={props.proposals}
        loadPlans={props.loadPlans}
        datasetId={props.datasetId}
        refreshKey={readinessKey}
        onStart={startAnalysis}
        onNavigate={handleReadinessNavigate}
        t={props.t}
      />
      <GuidedStageNav tabs={tabs} step={step} selected={props.selected} onStep={setStep} t={props.t} />
      <div className={`guided-stage ${focusCode ? `action-focus-${focusCode}` : ""}`}>
        {step === "upload" && (
          <UploadPane
            disabled={false}
            files={props.files}
            onUpload={props.onUpload}
            onDelete={props.onDelete}
            onRefresh={props.onRefreshFiles}
            onStart={startAnalysis}
            t={props.t}
          />
        )}
        {step === "analyze" && <JobProgress job={props.job} events={props.events} t={props.t} />}
        {step === "summary" && (
          <SummaryPane
            datasetId={props.datasetId}
            summaries={props.summaries}
            onRefresh={props.onRefreshSummaries}
            t={props.t}
          />
        )}
        {step === "destination" && (
          <div className="flow-stack">
            <ReviewPane
              datasetId={props.datasetId}
              reviews={props.reviews}
              summaries={props.summaries}
              onRefresh={props.onRefreshReviews}
              onConfirm={props.onConfirmReview}
              t={props.t}
            />
            <SchemaPane
              datasetId={props.datasetId}
              proposals={props.proposals}
              onRefresh={props.onRefreshProposals}
              onApprove={props.onApproveSchema}
              t={props.t}
            />
            <SchemaChatPane disabled={props.disabled} onAsk={props.onSchemaChat} onUseProposal={useChatProposal} t={props.t} />
          </div>
        )}
        {step === "load" && (
          <LoadPane
            connections={props.connections}
            files={props.files}
            tables={props.tables}
            reviews={props.reviews}
            plans={props.loadPlans}
            datasetId={props.datasetId}
            onCreatePlan={props.onCreateLoadPlan}
            onUpdateRows={props.onUpdateLoadPlanRows}
            onConfirm={props.onConfirmLoadPlan}
            t={props.t}
          />
        )}
        {step === "search" && <SearchPane datasetId={props.datasetId} disabled={props.disabled} onSearch={props.onSearch} onAsk={props.onAsk} t={props.t} />}
      </div>
      <WorkflowInspector
        datasetId={props.datasetId}
        files={props.files}
        summaries={props.summaries}
        reviews={props.reviews}
        proposals={props.proposals}
        loadPlans={props.loadPlans}
        refreshKey={readinessKey}
        onNavigate={handleReadinessNavigate}
        onRefreshReviews={props.onRefreshReviews}
        onApproveSchema={props.onApproveSchema}
        t={props.t}
      />
    </>
  );
}

function handleReadinessNavigateFactory(setStep: (step: Step) => void, setFocusCode: (code: string) => void) {
  return (value: string, action?: ReadinessAction) => {
    setStep(goToStep(value));
    setFocusCode(action?.code ?? "");
  };
}

function schemaFromProposal(proposal: Record<string, unknown>) {
  const columns = Array.isArray(proposal.columns) ? proposal.columns : [];
  return {
    description: String(proposal.assistant_message ?? proposal.description ?? ""),
    target_columns: columns.map(normalizeColumn).filter(Boolean),
    source_references_required: true,
  };
}

function goToStep(value: string) {
  if (["upload", "analyze", "summary", "destination", "load", "search"].includes(value)) {
    return value as Step;
  }
  return "upload";
}

function normalizeColumn(column: unknown) {
  if (!column || typeof column !== "object") return undefined;
  const value = column as Record<string, unknown>;
  const name = safeColumnName(String(value.name ?? ""));
  if (!name) return undefined;
  return { name, type: String(value.type ?? "text"), required: Boolean(value.required) };
}

function safeTableName(value: string) {
  return safeColumnName(value) || "custom_records";
}

function safeColumnName(value: string) {
  return value.trim().toLowerCase().replace(/[^a-z0-9_]+/g, "_").replace(/^_+|_+$/g, "").slice(0, 60);
}
