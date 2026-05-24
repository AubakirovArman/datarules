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

export type SimpleStep = "documents" | "analysis" | "destination" | "agent";

export type SimpleFlowProps = {
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
