import type {
  DocumentFile,
  DocumentReview,
  DocumentSummary,
  SchemaProposal,
  LoadPlan,
} from "@shared/types";
import { api } from "@shared/api";

export type LoadResults = {
  files: DocumentFile[];
  proposals: SchemaProposal[];
  reviews: DocumentReview[];
  summaries: DocumentSummary[];
  loadPlans: LoadPlan[];
};

export async function loadDatasetParts(datasetId: string, language: string): Promise<LoadResults> {
  const [files, proposals, reviews, summaries, loadPlans] = await Promise.all([
    api.files(datasetId),
    api.proposals(datasetId),
    api.reviews(datasetId),
    api.summaries(datasetId, language),
    api.loadPlans(datasetId),
  ] as const);

  return {
    files,
    proposals,
    reviews,
    summaries,
    loadPlans,
  };
}
