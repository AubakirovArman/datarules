import { useEffect, useState } from "react";
import { api } from "@shared/api";
import { loadDatasetParts } from "./controllerLoads";
import type { AppController, ControllerConfig } from "./appControllerTypes";
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
  TableCatalog,
} from "@shared/types";

export function useAppController({ t, language, onNavigateFlow }: ControllerConfig): AppController {
  const [datasets, setDatasets] = useState<Dataset[]>([]);
  const [selected, setSelected] = useState<Dataset | undefined>();
  const [files, setFiles] = useState<DocumentFile[]>([]);
  const [job, setJob] = useState<Job | undefined>();
  const [events, setEvents] = useState<JobEvent[]>([]);
  const [proposals, setProposals] = useState<SchemaProposal[]>([]);
  const [reviews, setReviews] = useState<DocumentReview[]>([]);
  const [summaries, setSummaries] = useState<DocumentSummary[]>([]);
  const [loadPlans, setLoadPlans] = useState<LoadPlan[]>([]);
  const [connections, setConnections] = useState<DbConnection[]>([]);
  const [tables, setTables] = useState<TableCatalog[]>([]);
  const [health, setHealth] = useState<Record<string, unknown>>({});
  const [error, setError] = useState("");

  const selectedDisabled = !selected;

  useEffect(() => {
    runSafe(async () => {
      setHealth(await api.health());
      await loadDatasets();
      await loadDbSettings();
    });
  }, []);

  useEffect(() => {
    if (!selected) return;
    runSafe(() => refreshLoaders(selected));
  }, [selected?.id, language]);

  useEffect(() => {
    if (!job) return;
    const timer = window.setInterval(() => {
      void runSafe(async () => {
        const nextJob = await api.job(job.id);
        const nextEvents = await api.events(job.id);
        setJob(nextJob);
        setEvents(nextEvents);
        if (["waiting_review", "completed", "failed", "cancelled"].includes(nextJob.status)) {
          await refreshLoaders(selected);
          window.clearInterval(timer);
        }
      });
    }, 1200);
    return () => window.clearInterval(timer);
  }, [job?.id, selected?.id]);

  function clearError() {
    setError("");
  }

  async function runSafe<T>(operation: () => Promise<T>): Promise<T | undefined> {
    clearError();
    try {
      return await operation();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
      return undefined;
    }
  }

  async function loadDatasets() {
    const items = await api.datasets();
    setDatasets(items);
    setSelected((current) => current ?? items[0]);
  }

  async function loadDbSettings() {
    setConnections(await api.connections());
    setTables(await api.tableCatalog());
  }

  async function refreshFiles(dataset = selected) {
    if (!dataset) return;
    setFiles(await api.files(dataset.id));
  }

  async function refreshProposals(dataset = selected) {
    if (!dataset) return;
    setProposals(await api.proposals(dataset.id));
  }

  async function refreshReviews(dataset = selected) {
    if (!dataset) return;
    setReviews(await api.reviews(dataset.id));
  }

  async function refreshSummaries(dataset = selected) {
    if (!dataset) return;
    setSummaries(await api.summaries(dataset.id, language));
  }

  async function refreshLoadPlans(dataset = selected) {
    if (!dataset) return;
    setLoadPlans(await api.loadPlans(dataset.id));
  }

  async function refreshLoaders(dataset = selected) {
    if (!dataset) return;
    const results = await loadAll(dataset);
    setFiles(results.files);
    setProposals(results.proposals);
    setReviews(results.reviews);
    setSummaries(results.summaries);
    setLoadPlans(results.loadPlans);
  }

  async function loadAll(dataset = selected) {
    if (!dataset) throw new Error("Select a dataset first");
    return loadDatasetParts(dataset.id, language);
  }

  async function ensureDataset() {
    if (selected) return selected;
    const dataset = await api.createDataset(t("autoDatasetName"), t("autoDatasetDescription"));
    setSelected(dataset);
    setDatasets((items) => [dataset, ...items]);
    return dataset;
  }

  async function createDataset(name: string, description: string) {
    await runSafe(async () => {
      const dataset = await api.createDataset(name, description);
      await loadDatasets();
      setSelected(dataset);
      onNavigateFlow();
    });
  }

  function selectDataset(dataset: Dataset) {
    setSelected(dataset);
    setJob(undefined);
    setEvents([]);
    onNavigateFlow();
  }

  async function onUpload(uploads: FileList) {
    return runSafe(async () => {
      const dataset = await ensureDataset();
      await api.upload(dataset.id, uploads);
      await refreshFiles(dataset);
    });
  }

  async function onDelete(documentId: string) {
    return runSafe(async () => {
      if (!selected) return;
      await api.deleteFile(selected.id, documentId);
      await Promise.all([refreshFiles(), refreshReviews(), refreshSummaries(), refreshLoadPlans()]);
    });
  }

  async function onStart() {
    const nextJob = await runSafe(async () => {
      if (!selected) throw new Error(t("uploadFirst"));
      return api.startJob(selected.id);
    });
    if (nextJob) {
      setJob(nextJob);
      setEvents(await api.events(nextJob.id));
    }
    return nextJob;
  }

  async function onConfirmReview(id: string, selectedDocType: string, selectedTable: string, notes: string) {
    return runSafe(async () => {
      await api.decideReview(id, selectedDocType, selectedTable, notes);
      await Promise.all([refreshReviews(), refreshLoadPlans()]);
    }).then(() => undefined);
  }

  async function onApproveSchema(id: string) {
    return runSafe(async () => {
      await api.approve(id);
      await refreshProposals();
    }).then(() => undefined);
  }

  async function onSchemaChat(message: string): Promise<SchemaChatResponse> {
    const result = await runSafe(async () => {
      if (!selected) throw new Error("Select a dataset first");
      return api.schemaChat(selected.id, message, language);
    });
    if (!result) throw new Error("Schema chat failed");
    return result;
  }

  async function onCreateLoadPlan(
    connectionId: string | undefined,
    schema: string,
    mode: string,
    table: string,
    planSchema?: Record<string, unknown>,
    documentIds?: string[],
    schemaVersionId?: string,
  ) {
    const plan = await runSafe(async () => {
      if (!selected) throw new Error("Select a dataset first");
      return api.createLoadPlan(selected.id, connectionId, schema, mode, table, planSchema, documentIds, schemaVersionId);
    });
    if (plan) await refreshLoadPlans();
    return plan;
  }

  async function onUpdateLoadPlanRows(planId: string, rows: LoadPlan["preview_rows"]) {
    return runSafe(async () => {
      await api.updateLoadPlanRows(planId, rows);
      await refreshLoadPlans();
    }).then(() => undefined);
  }

  async function onConfirmLoadPlan(planId: string) {
    return runSafe(async () => {
      await api.confirmLoadPlan(planId);
      await refreshLoadPlans();
    }).then(() => undefined);
  }

  async function onSearch(query: string) {
    const result = await runSafe(async () => {
      if (!selected) throw new Error("Select a dataset first");
      return api.search(selected.id, query);
    });
    return result ?? [];
  }

  async function onAsk(query: string): Promise<AskResponse> {
    const result = await runSafe(async () => {
      if (!selected) throw new Error("Select a dataset first");
      return api.ask(selected.id, query);
    });
    if (!result) throw new Error("Ask failed");
    return result;
  }

  return {
    datasets,
    selected,
    files,
    job,
    events,
    proposals,
    reviews,
    summaries,
    loadPlans,
    connections,
    tables,
    health,
    error,
    selectedDisabled,
    createDataset,
    selectDataset,
    refreshFiles: () => runSafe(() => refreshFiles(selected)),
    loadDatasets,
    loadDbSettings,
    refreshReviews: () => runSafe(() => refreshReviews(selected)),
    refreshSummaries: () => runSafe(() => refreshSummaries(selected)),
    refreshProposals: () => runSafe(() => refreshProposals(selected)),
    refreshLoadPlans: () => runSafe(() => refreshLoadPlans(selected)),
    onUpload,
    onDelete,
    onRefreshFiles: () => runSafe(() => refreshFiles(selected)),
    onStart,
    onRefreshSummaries: () => runSafe(() => refreshSummaries(selected)),
    onRefreshReviews: () => runSafe(() => refreshReviews(selected)),
    onConfirmReview,
    onRefreshProposals: () => runSafe(() => refreshProposals(selected)),
    onApproveSchema,
    onSchemaChat,
    onCreateLoadPlan,
    onUpdateLoadPlanRows,
    onConfirmLoadPlan,
    onSearch,
    onAsk,
    setJob,
    clearError,
  };
}
