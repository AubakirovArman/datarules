import type { Language } from "@shared/i18n";
import type {
  AskResponse,
  Dataset,
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

export type ControllerConfig = {
  t: (key: string) => string;
  language: Language;
  onNavigateFlow: () => void;
};

export type AppController = {
  datasets: Dataset[];
  selected?: Dataset;
  files: DocumentFile[];
  job?: Job;
  events: JobEvent[];
  proposals: SchemaProposal[];
  reviews: DocumentReview[];
  summaries: DocumentSummary[];
  loadPlans: LoadPlan[];
  connections: DbConnection[];
  tables: TableCatalog[];
  health: Record<string, unknown>;
  error: string;
  selectedDisabled: boolean;
  createDataset: (name: string, description: string) => Promise<void>;
  selectDataset: (dataset: Dataset) => void;
  refreshFiles: () => Promise<void | undefined>;
  loadDatasets: () => Promise<void>;
  loadDbSettings: () => Promise<void>;
  refreshReviews: () => Promise<void | undefined>;
  refreshSummaries: () => Promise<void | undefined>;
  refreshProposals: () => Promise<void | undefined>;
  refreshLoadPlans: () => Promise<void | undefined>;
  onUpload: (uploads: FileList) => Promise<void | undefined>;
  onDelete: (documentId: string) => Promise<void | undefined>;
  onRefreshFiles: () => Promise<void | undefined>;
  onStart: () => Promise<Job | undefined>;
  onRefreshSummaries: () => Promise<void | undefined>;
  onRefreshReviews: () => Promise<void | undefined>;
  onConfirmReview: (id: string, docType: string, table: string, notes: string) => Promise<void>;
  onRefreshProposals: () => Promise<void | undefined>;
  onApproveSchema: (id: string) => Promise<void>;
  onSchemaChat: (message: string) => Promise<SchemaChatResponse>;
  onCreateLoadPlan: (
    connectionId: string | undefined,
    schema: string,
    mode: string,
    table: string,
    planSchema?: Record<string, unknown>,
    documentIds?: string[],
    schemaVersionId?: string,
  ) => Promise<LoadPlan | undefined>;
  onUpdateLoadPlanRows: (planId: string, rows: LoadPlan["preview_rows"]) => Promise<void>;
  onConfirmLoadPlan: (planId: string) => Promise<void>;
  onSearch: (query: string) => Promise<SearchHit[]>;
  onAsk: (query: string) => Promise<AskResponse>;
  setJob: (job?: Job) => void;
  clearError: () => void;
};
