import { X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@shared/api";

type Props = {
  datasetId: string;
  documentId: string;
  runId: string;
  onClose: () => void;
  t: (key: string) => string;
};

export function ExtractionRunDiffView({ datasetId, documentId, runId, onClose, t }: Props) {
  const [diff, setDiff] = useState<Record<string, unknown>>();
  const [error, setError] = useState("");
  useEffect(() => {
    setDiff(undefined);
    setError("");
    api.extractionRunDiff(datasetId, documentId, runId).then(setDiff).catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [datasetId, documentId, runId]);
  if (error) return <small className="load-save-warning">{error}</small>;
  if (!diff) return <small>{loadingLabel(t)}</small>;
  const summary = objectValue(diff.summary);
  const changed = recordArray(diff.changed_blocks);
  const added = recordArray(diff.added_blocks);
  const removed = recordArray(diff.removed_blocks);
  return (
    <div className="extraction-diff">
      <div className="diff-head">
        <strong>{diffLabel(t)}</strong>
        <button onClick={onClose} type="button"><X size={13} /></button>
      </div>
      <div className="metric-row">
        <MiniMetric label={changedLabel(t)} value={summary.changed_blocks} />
        <MiniMetric label={addedLabel(t)} value={summary.added_blocks} />
        <MiniMetric label={removedLabel(t)} value={summary.removed_blocks} />
      </div>
      {[...changed, ...added, ...removed].slice(0, 5).map((item, index) => {
        const before = String(item.before_text ?? "");
        const after = String(item.after_text ?? "");
        const text = String(item.text ?? "");
        return (
          <div className="diff-change" key={`${String(item.key ?? "")}-${index}`}>
            <small>{locationText(objectValue(item.location))} · {String(item.block_type ?? item.status ?? "")}</small>
            {before && <p><b>{beforeLabel(t)}:</b> {before}</p>}
            {after && <p><b>{afterLabel(t)}:</b> {after}</p>}
            {text && <p>{text}</p>}
          </div>
        );
      })}
    </div>
  );
}

function MiniMetric({ label, value }: { label: string; value: unknown }) {
  return (
    <span className="mini-metric">
      <strong>{String(value ?? 0)}</strong>
      <small>{label}</small>
    </span>
  );
}

function locationText(location: Record<string, unknown>) {
  if (location.page) return `page ${String(location.page)}`;
  if (location.sheet_name) return `sheet ${String(location.sheet_name)}`;
  if (location.slide_number) return `slide ${String(location.slide_number)}`;
  return "document";
}

function diffLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "Айырмашылық";
  if (language === "Language") return "Run diff";
  return "Разница прогонов";
}

function loadingLabel(t: Props["t"]) {
  return t("language") === "Language" ? "Loading diff..." : "Загрузка diff...";
}

function changedLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "өзгерді";
  if (language === "Language") return "changed";
  return "изменено";
}

function addedLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "қосылды";
  if (language === "Language") return "added";
  return "добавлено";
}

function removedLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "жойылды";
  if (language === "Language") return "removed";
  return "удалено";
}

function beforeLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "бұрын";
  if (language === "Language") return "before";
  return "было";
}

function afterLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "кейін";
  if (language === "Language") return "after";
  return "стало";
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function recordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item) => typeof item === "object") as Array<Record<string, unknown>> : [];
}
