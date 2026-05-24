import { CheckCircle2, ChevronLeft, ChevronRight, RotateCcw, Save, ShieldCheck, XCircle } from "lucide-react";
import { useEffect, useState } from "react";
import type { LoadPlan } from "@shared/types";
import { PreviewFieldNotes, PreviewSourceEvidence } from "./PreviewSourceEvidence";

type Props = {
  plan: LoadPlan;
  onSave: (rows: LoadPlan["preview_rows"]) => Promise<void>;
  onDirtyChange?: (dirty: boolean) => void;
  t: (key: string) => string;
};

const PAGE_SIZE = 8;
const FILTERS = ["all", "candidate", "approved", "needs_review", "rejected"];

export function PreviewEditor({ plan, onSave, onDirtyChange, t }: Props) {
  const [rows, setRows] = useState(plan.preview_rows);
  const [busy, setBusy] = useState(false);
  const [filter, setFilter] = useState("all");
  const [page, setPage] = useState(0);

  useEffect(() => {
    setRows(plan.preview_rows);
    setPage(0);
  }, [plan.id, plan.preview_rows]);

  useEffect(() => {
    setPage(0);
  }, [filter]);

  const dirty = JSON.stringify(rows) !== JSON.stringify(plan.preview_rows);

  useEffect(() => {
    onDirtyChange?.(dirty);
  }, [dirty, onDirtyChange]);

  async function save() {
    setBusy(true);
    try {
      await onSave(rows);
    } finally {
      setBusy(false);
    }
  }

  const indexedRows = rows.map((row, index) => ({ row, index }));
  const filtered = indexedRows.filter((item) => filter === "all" || rowStatus(item.row) === filter);
  const pageCount = Math.max(1, Math.ceil(filtered.length / PAGE_SIZE));
  const safePage = Math.min(page, pageCount - 1);
  const visible = filtered.slice(safePage * PAGE_SIZE, safePage * PAGE_SIZE + PAGE_SIZE);
  const stats = rowStats(rows);
  const visibleIndexes = visible.map((item) => item.index);

  return (
    <div className="preview-table">
      <div className="preview-toolbar">
        <strong>{t("preview")}</strong>
        <span className="preview-counts">
          {t("visibleRows")}: {filtered.length} / {rows.length}
        </span>
        {dirty && <span className="unsaved-preview">{t("unsavedPreview")}</span>}
        <button disabled={busy || plan.status === "loaded"} onClick={save}>
          <Save size={15} />
          <span>{t("savePreview")}</span>
        </button>
      </div>
      <div className="preview-filterbar">
        <select value={filter} onChange={(event) => setFilter(event.target.value)}>
          {FILTERS.map((item) => (
            <option value={item} key={item}>
              {item === "all" ? t("allRows") : `${t(item)} ${stats[item] ?? 0}`}
            </option>
          ))}
        </select>
        <div className="bulk-row-actions">
          <button disabled={busy || plan.status === "loaded"} onClick={() => setRows(rows.map(approveSafeRow))}>
            <ShieldCheck size={14} />
            <span>{t("approveSafeRows")}</span>
          </button>
          <button disabled={busy || plan.status === "loaded"} onClick={() => setRows(updateRows(rows, visibleIndexes, "approved"))}>
            <CheckCircle2 size={14} />
            <span>{t("approveVisible")}</span>
          </button>
          <button disabled={busy || plan.status === "loaded"} onClick={() => setRows(updateRows(rows, visibleIndexes, "rejected"))}>
            <XCircle size={14} />
            <span>{t("rejectVisible")}</span>
          </button>
          <button disabled={busy || plan.status === "loaded"} onClick={() => setRows(updateRows(rows, visibleIndexes, "candidate"))}>
            <RotateCcw size={14} />
            <span>{t("resetVisible")}</span>
          </button>
        </div>
        <div className="preview-pages">
          <button disabled={safePage <= 0} onClick={() => setPage(Math.max(0, safePage - 1))} title={t("prevPage")}>
            <ChevronLeft size={14} />
          </button>
          <span>{t("page")} {safePage + 1} / {pageCount}</span>
          <button disabled={safePage >= pageCount - 1} onClick={() => setPage(Math.min(pageCount - 1, safePage + 1))} title={t("nextPage")}>
            <ChevronRight size={14} />
          </button>
        </div>
      </div>
      {visible.map(({ row, index }) => (
        <EditableRow
          key={String(row.row_id ?? index)}
          planId={plan.id}
          row={row}
          onChange={(next) => setRows(rows.map((item, itemIndex) => (itemIndex === index ? next : item)))}
          t={t}
        />
      ))}
    </div>
  );
}

function EditableRow({
  planId,
  row,
  onChange,
  t,
}: {
  planId: string;
  row: Record<string, unknown>;
  onChange: (row: Record<string, unknown>) => void;
  t: Props["t"];
}) {
  const fields = fieldValues(row);
  const explain = objectValue(row.explainability);
  const coverage = objectValue(explain.field_coverage);
  const notes = Array.isArray(explain.field_notes) ? explain.field_notes : [];
  return (
    <div className={`preview-edit-row ${String(row.row_status ?? "candidate")}`}>
      <div className="preview-row-head">
        <span>{String(row.source_file ?? "")}</span>
        <small>
          {row.page ? `page ${String(row.page)}` : ""}
          {row.confidence ? ` · ${String(row.confidence)}` : ""}
        </small>
      </div>
      <div className="row-review-actions">
        <span className="row-status">{t(String(row.row_status ?? "candidate"))}</span>
        <button onClick={() => onChange(setRowStatus(row, "approved"))} title={t("approveRow")}>
          <CheckCircle2 size={14} />
          <span>{t("approveRow")}</span>
        </button>
        <button onClick={() => onChange(setRowStatus(row, "rejected"))} title={t("rejectRow")}>
          <XCircle size={14} />
          <span>{t("rejectRow")}</span>
        </button>
        <button onClick={() => onChange(setRowStatus(row, "candidate"))} title={t("resetRow")}>
          <RotateCcw size={14} />
          <span>{t("resetRow")}</span>
        </button>
      </div>
      {Object.keys(explain).length > 0 && (
        <div className="preview-explain">
          <strong>{t(String(explain.status ?? "ready"))}</strong>
          <span>{String(explain.why_row_selected ?? "")}</span>
          <small>{t("fields")}: {String(coverage.filled ?? 0)} / {String(coverage.total ?? 0)}</small>
        </div>
      )}
      <textarea
        value={String(row.content ?? row.field_text ?? "")}
        onChange={(event) => onChange({ ...row, content: event.target.value, field_text: event.target.value })}
        placeholder={t("content")}
      />
      <div className="field-editor-grid">
        {fields.map(([key, value]) => (
          <label key={key}>
            <span>{key}</span>
            <input
              value={value == null ? "" : String(value)}
              onChange={(event) => onChange(updateField(row, key, event.target.value))}
            />
          </label>
        ))}
      </div>
      {Array.isArray(row.validation_errors) && row.validation_errors.length > 0 && (
        <small className="warning">{row.validation_errors.join(", ")}</small>
      )}
      <PreviewFieldNotes notes={notes} t={t} />
      <PreviewSourceEvidence planId={planId} row={row} notes={notes} t={t} />
    </div>
  );
}

function fieldValues(row: Record<string, unknown>) {
  const values = row.field_values;
  if (!values || typeof values !== "object" || Array.isArray(values)) return [];
  return Object.entries(values as Record<string, unknown>);
}

function updateField(row: Record<string, unknown>, key: string, value: string) {
  const values = fieldValues(row).reduce<Record<string, unknown>>((items, [field, fieldValue]) => {
    items[field] = field === key ? value || null : fieldValue;
    return items;
  }, {});
  return { ...row, field_values: values };
}

function setRowStatus(row: Record<string, unknown>, status: string) {
  return { ...row, row_status: status, edited_by_user: true };
}

function approveSafeRow(row: Record<string, unknown>) {
  if (!isSafeRow(row) || rowStatus(row) === "rejected") return row;
  return setRowStatus(row, "approved");
}

function updateRows(rows: Array<Record<string, unknown>>, indexes: number[], status: string) {
  const selected = new Set(indexes);
  return rows.map((row, index) => {
    if (!selected.has(index)) return row;
    if (status === "approved" && !isSafeRow(row)) return row;
    return setRowStatus(row, status);
  });
}

function isSafeRow(row: Record<string, unknown>) {
  const errors = row.validation_errors;
  if (Array.isArray(errors) && errors.length > 0) return false;
  return confidence(row) >= 0.75;
}

function confidence(row: Record<string, unknown>) {
  const value = Number(row.confidence ?? 0);
  return Number.isFinite(value) ? value : 0;
}

function rowStatus(row: Record<string, unknown>) {
  return String(row.row_status ?? "candidate");
}

function rowStats(rows: Array<Record<string, unknown>>) {
  return rows.reduce<Record<string, number>>((stats, row) => {
    const key = rowStatus(row);
    stats[key] = (stats[key] ?? 0) + 1;
    return stats;
  }, {});
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}
