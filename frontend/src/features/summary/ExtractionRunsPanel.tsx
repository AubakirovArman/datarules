import { GitCompareArrows, History, RotateCcw } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@shared/api";
import { ExtractionRunDiffView } from "./ExtractionRunDiffView";

type Props = {
  datasetId: string;
  documentId: string;
  onChanged?: () => Promise<void>;
  t: (key: string) => string;
};

export function ExtractionRunsPanel({ datasetId, documentId, onChanged, t }: Props) {
  const [runs, setRuns] = useState<Array<Record<string, unknown>>>([]);
  const [busy, setBusy] = useState("");
  const [diffRunId, setDiffRunId] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    void refresh(datasetId, documentId, setRuns);
  }, [datasetId, documentId]);
  if (!runs.length) return null;
  const latestId = String(runs[0]?.id ?? "");
  return (
    <div className="route-evidence extraction-runs">
      <em><History size={13} /> {label(t)}</em>
      {error && <small className="load-save-warning">{error}</small>}
      {runs.slice(0, 4).map((run) => {
        const runId = String(run.id ?? "");
        const quality = objectValue(run.quality);
        const metrics = objectValue(run.metrics);
        const canRollback = runId && runId !== latestId;
        const canCompare = runId && runs.length > 1;
        return (
          <span key={runId}>
            {String(run.run_type ?? "")} · {String(run.status ?? "")} · {String(quality.extraction_score ?? "-")}%
            {` · ${String(metrics.blocks ?? 0)} ${blocksLabel(t)}`}
            {canCompare && (
              <button disabled={Boolean(busy)} onClick={() => setDiffRunId(diffRunId === runId ? "" : runId)} type="button">
                <GitCompareArrows size={13} /> {diffLabel(t)}
              </button>
            )}
            {canRollback && (
              <button disabled={Boolean(busy)} onClick={() => void rollback(datasetId, documentId, runId, setBusy, setError, setRuns, onChanged)} type="button">
                <RotateCcw size={13} /> {busy === runId ? busyLabel(t) : rollbackLabel(t)}
              </button>
            )}
          </span>
        );
      })}
      {diffRunId && <ExtractionRunDiffView datasetId={datasetId} documentId={documentId} runId={diffRunId} onClose={() => setDiffRunId("")} t={t} />}
    </div>
  );
}

async function rollback(
  datasetId: string,
  documentId: string,
  runId: string,
  setBusy: (value: string) => void,
  setError: (value: string) => void,
  setRuns: (value: Array<Record<string, unknown>>) => void,
  onChanged?: () => Promise<void>,
) {
  setBusy(runId);
  setError("");
  try {
    await api.rollbackExtractionRun(datasetId, documentId, runId);
    await onChanged?.();
    await refresh(datasetId, documentId, setRuns);
  } catch (error) {
    setError(error instanceof Error ? error.message : String(error));
  } finally {
    setBusy("");
  }
}

async function refresh(
  datasetId: string,
  documentId: string,
  setRuns: (value: Array<Record<string, unknown>>) => void,
) {
  const response = await api.extractionRuns(datasetId, documentId);
  setRuns(recordArray(response.runs));
}

function label(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "Шығару тарихы";
  if (language === "Language") return "Extraction history";
  return "История извлечения";
}

function rollbackLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "қайтару";
  if (language === "Language") return "rollback";
  return "откатить";
}

function diffLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "салыстыру";
  if (language === "Language") return "diff";
  return "сравнить";
}

function busyLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "қайтаруда";
  if (language === "Language") return "rolling back";
  return "откат";
}

function blocksLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "блок";
  if (language === "Language") return "blocks";
  return "блоков";
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function recordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item) => typeof item === "object") as Array<Record<string, unknown>> : [];
}
