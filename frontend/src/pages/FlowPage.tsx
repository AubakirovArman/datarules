import type {
  AskResponse,
  DbConnection,
  DocumentFile,
  DocumentReview,
  DocumentSummary,
  Job,
  JobEvent,
  LoadPlan,
  SchemaChatResponse,
  SchemaProposal,
  SearchHit,
  TableCatalog,
} from "@shared/types";
import { GuidedFlow } from "@features/workflow/GuidedFlow";

type Props = {
  selected: boolean;
  disabled: boolean;
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
  onUpload: (files: FileList) => Promise<void>;
  onDelete: (documentId: string) => Promise<void>;
  onRefreshFiles: () => Promise<void>;
  onStart: () => Promise<Job | undefined>;
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

export function FlowPage({
  selected,
  disabled,
  files,
  job,
  events,
  summaries,
  reviews,
  proposals,
  loadPlans,
  connections,
  tables,
  datasetId,
  onUpload,
  onDelete,
  onRefreshFiles,
  onStart,
  onRefreshSummaries,
  onRefreshReviews,
  onConfirmReview,
  onRefreshProposals,
  onApproveSchema,
  onSchemaChat,
  onCreateLoadPlan,
  onUpdateLoadPlanRows,
  onConfirmLoadPlan,
  onSearch,
  onAsk,
  t,
}: Props) {
  return (
    <GuidedFlow
      selected={selected}
      disabled={disabled}
      files={files}
      job={job}
      events={events}
      summaries={summaries}
      reviews={reviews}
      proposals={proposals}
      loadPlans={loadPlans}
      connections={connections}
      tables={tables}
      datasetId={datasetId}
      onUpload={onUpload}
      onDelete={onDelete}
      onRefreshFiles={onRefreshFiles}
      onStart={onStart}
      onRefreshSummaries={onRefreshSummaries}
      onRefreshReviews={onRefreshReviews}
      onConfirmReview={onConfirmReview}
      onRefreshProposals={onRefreshProposals}
      onApproveSchema={onApproveSchema}
      onSchemaChat={onSchemaChat}
      onCreateLoadPlan={onCreateLoadPlan}
      onUpdateLoadPlanRows={onUpdateLoadPlanRows}
      onConfirmLoadPlan={onConfirmLoadPlan}
      onSearch={onSearch}
      onAsk={onAsk}
      t={t}
    />
  );
}
