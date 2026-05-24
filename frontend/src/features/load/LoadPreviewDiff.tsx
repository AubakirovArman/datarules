import { GitCompareArrows, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@shared/api";

type Props = {
  planId: string;
  onClose: () => void;
  t: (key: string) => string;
};

export function LoadPreviewDiff({ planId, onClose, t }: Props) {
  const [diff, setDiff] = useState<Record<string, unknown>>();
  const [error, setError] = useState("");
  useEffect(() => {
    setDiff(undefined);
    setError("");
    api.loadPlanPreviewDiff(planId).then(setDiff).catch((err) => setError(err instanceof Error ? err.message : String(err)));
  }, [planId]);
  if (error) return <small className="load-save-warning">{error}</small>;
  if (!diff) return <small>{loadingLabel(t)}</small>;
  const summary = objectValue(diff.summary);
  const changed = recordArray(diff.changed_rows);
  const added = recordArray(diff.added_rows);
  const removed = recordArray(diff.removed_rows);
  const issueDelta = objectValue(diff.issue_delta);
  return (
    <div className="load-preview-diff">
      <div className="diff-head">
        <strong><GitCompareArrows size={14} /> {titleLabel(t)}</strong>
        <button onClick={onClose} type="button"><X size={13} /></button>
      </div>
      <div className="metric-row">
        <Metric label={changedLabel(t)} value={summary.changed_rows} />
        <Metric label={addedLabel(t)} value={summary.added_rows} />
        <Metric label={removedLabel(t)} value={summary.removed_rows} />
        <Metric label={errorsLabel(t)} value={`${String(summary.current_errors ?? 0)} -> ${String(summary.fresh_errors ?? 0)}`} />
      </div>
      <small>
        {loadableLabel(t)}: {String(summary.current_loadable ?? 0)} {"->"} {String(summary.fresh_loadable ?? 0)}
        {` · ${issuesLabel(t)}: +${recordArray(issueDelta.added).length} / -${recordArray(issueDelta.resolved).length}`}
      </small>
      {[...changed, ...added, ...removed].slice(0, 5).map((row, index) => <RowChange row={row} t={t} key={`${String(row.row_id ?? "")}-${index}`} />)}
    </div>
  );
}

function RowChange({ row, t }: { row: Record<string, unknown>; t: Props["t"] }) {
  const before = String(row.before_content ?? "");
  const after = String(row.after_content ?? "");
  const text = String(row.content ?? "");
  const fields = recordArray(row.field_changes);
  return (
    <div className="preview-diff-row">
      <small>{String(row.source_file ?? "")} · {String(row.row_id ?? "")}</small>
      {fields.slice(0, 4).map((field) => (
        <p key={String(field.field)}>
          <b>{String(field.field)}:</b> {String(field.before ?? "")} {"->"} {String(field.after ?? "")}
        </p>
      ))}
      {Boolean(row.source_changed) && <p><b>{sourceLabel(t)}:</b> {String(row.before_source_block_id ?? "")} {"->"} {String(row.after_source_block_id ?? "")}</p>}
      {before && <p><b>{beforeLabel(t)}:</b> {before}</p>}
      {after && <p><b>{afterLabel(t)}:</b> {after}</p>}
      {text && <p>{text}</p>}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: unknown }) {
  return <span className="mini-metric"><strong>{String(value ?? 0)}</strong><small>{label}</small></span>;
}

function titleLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "Preview салыстыру";
  if (language === "Language") return "Preview diff";
  return "Сравнение preview";
}

function loadingLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "Preview салыстыру...";
  if (language === "Language") return "Building preview diff...";
  return "Сравнение preview...";
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

function errorsLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "қате";
  if (language === "Language") return "errors";
  return "ошибки";
}

function loadableLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "жүктеуге болады";
  if (language === "Language") return "loadable";
  return "можно залить";
}

function issuesLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "тексеру";
  if (language === "Language") return "issues";
  return "проверки";
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

function sourceLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "дереккөзі";
  if (language === "Language") return "source";
  return "источник";
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function recordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item) => typeof item === "object") as Array<Record<string, unknown>> : [];
}
