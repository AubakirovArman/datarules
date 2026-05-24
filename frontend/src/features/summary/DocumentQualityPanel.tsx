import { AlertTriangle, CheckCircle2, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@shared/api";
import { ExtractionRunsPanel } from "./ExtractionRunsPanel";

type Props = {
  datasetId?: string;
  refreshKey: string;
  onRepair?: () => Promise<void>;
  t: (key: string) => string;
};

export function DocumentQualityPanel({ datasetId, refreshKey, onRepair, t }: Props) {
  const [report, setReport] = useState<Record<string, unknown>>();
  const [busyDoc, setBusyDoc] = useState("");
  const [error, setError] = useState("");
  useEffect(() => {
    if (!datasetId) return;
    api.documentQuality(datasetId).then(setReport).catch(() => setReport(undefined));
  }, [datasetId, refreshKey]);
  if (!report) return null;
  const counts = objectValue(report.counts);
  const documents = recordArray(report.documents);
  return (
    <div className={`agent-plan ${report.status === "ready" ? "ready" : "attention"}`}>
      <strong>{icon(String(report.status))} {label(t)} · {String(report.status ?? "")}</strong>
      <div className="metric-row">
        <Metric label={t("files")} value={Number(counts.documents ?? 0)} />
        <Metric label={t("ready")} value={Number(counts.ready ?? 0)} />
        <Metric label={t("lowConfidence")} value={Number(counts.low_confidence_blocks ?? 0)} />
        <Metric label={t("pages")} value={Number(counts.image_pages_pending ?? 0)} />
      </div>
      {error && <small className="load-save-warning">{error}</small>}
      <div className="ai-summary-list">
        {documents.slice(0, 5).map((document) => (
          <DocumentRow
            busy={busyDoc === document.document_id}
            datasetId={datasetId}
            document={document}
            onRepair={onRepair}
            setBusyDoc={setBusyDoc}
            setError={setError}
            setReport={setReport}
            t={t}
            key={String(document.document_id)}
          />
        ))}
      </div>
    </div>
  );
}

function DocumentRow(props: {
  busy: boolean;
  datasetId?: string;
  document: Record<string, unknown>;
  onRepair?: () => Promise<void>;
  setBusyDoc: (value: string) => void;
  setError: (value: string) => void;
  setReport: (value: Record<string, unknown>) => void;
  t: Props["t"];
}) {
  const { busy, datasetId, document, onRepair, setBusyDoc, setError, setReport, t } = props;
  const quality = objectValue(document.quality);
  const actions = Array.isArray(document.actions) ? document.actions.map(String).join(", ") : "";
  const repairable = String(document.load_gate ?? "") !== "passed";
  const documentId = String(document.document_id);
  const onChanged = async () => {
    await onRepair?.();
    if (datasetId) setReport(await api.documentQuality(datasetId));
  };
  return (
    <div className="extraction-document-row">
      <strong>{String(document.file_name ?? "")}</strong>
      {` · ${String(document.load_gate ?? "")} · ${String(quality.extraction_score ?? 0)}%`}
      {actions ? ` · ${actionLabel(t)}: ${actions}` : ""}
      {repairable && datasetId && (
        <button disabled={busy} onClick={() => void repair(datasetId, documentId, setBusyDoc, setError, setReport, onRepair)} type="button">
          {repairLabel(t)}
        </button>
      )}
      {datasetId && <ExtractionRunsPanel datasetId={datasetId} documentId={documentId} onChanged={onChanged} t={t} />}
    </div>
  );
}

async function repair(datasetId: string, documentId: string, setBusyDoc: (value: string) => void, setError: (value: string) => void, setReport: (value: Record<string, unknown>) => void, onRepair?: () => Promise<void>) {
  setBusyDoc(documentId);
  setError("");
  try {
    await api.repairDocument(datasetId, documentId);
    await onRepair?.();
    setReport(await api.documentQuality(datasetId));
  } catch (error) {
    setError(error instanceof Error ? error.message : String(error));
  } finally {
    setBusyDoc("");
  }
}

function Metric({ label, value }: { label: string; value: number }) {
  return (
    <div className="metric">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}

function icon(status: string) {
  if (status === "ready") return <CheckCircle2 size={15} />;
  if (status === "blocked") return <ShieldAlert size={15} />;
  return <AlertTriangle size={15} />;
}

function label(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "Құжат сапасы";
  if (language === "Language") return "Document quality";
  return "Качество документов";
}

function actionLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "әрекет";
  if (language === "Language") return "action";
  return "действие";
}

function repairLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "қайта шығару";
  if (language === "Language") return "repair";
  return "починить";
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function recordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item) => typeof item === "object") as Array<Record<string, unknown>> : [];
}
