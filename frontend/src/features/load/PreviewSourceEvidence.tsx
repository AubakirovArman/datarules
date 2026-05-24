import { Eye, X } from "lucide-react";
import { useState } from "react";
import { api } from "@shared/api";

type Props = {
  planId: string;
  row: Record<string, unknown>;
  notes: unknown[];
  t: (key: string) => string;
};

export function PreviewSourceEvidence({ planId, row, notes, t }: Props) {
  const [source, setSource] = useState<Record<string, unknown>>();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  async function toggle() {
    if (source) {
      setSource(undefined);
      return;
    }
    setBusy(true);
    setError("");
    try {
      setSource(await api.previewRowSource(planId, rowId(row)));
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="preview-source">
      {notes.length > 0 && <FieldNotes notes={notes} t={t} />}
      <button disabled={busy} onClick={toggle} type="button">
        {source ? <X size={14} /> : <Eye size={14} />}
        <span>{source ? closeLabel(t) : sourceLabel(t)}</span>
      </button>
      {error && <small className="warning">{error}</small>}
      {source && <SourcePanel source={source} t={t} />}
    </div>
  );
}

function FieldNotes({ notes, t }: { notes: unknown[]; t: Props["t"] }) {
  const rows = evidenceRows(notes);
  if (rows.length === 0) return null;
  return (
    <div className="source-evidence-grid">
      <strong>{t("evidence")}</strong>
      {rows.slice(0, 4).map((row, index) => (
        <small key={`${row.field}-${index}`}>
          <span>{row.field} · {row.location}</span>
          {row.evidence}
        </small>
      ))}
    </div>
  );
}

function SourcePanel({ source, t }: { source: Record<string, unknown>; t: Props["t"] }) {
  const document = objectValue(source.document);
  const block = objectValue(source.block);
  const context = recordArray(source.context);
  const warnings = Array.isArray(source.warnings) ? source.warnings.map(String) : [];
  return (
    <div className="preview-source-panel">
      <strong>{String(document.file_name ?? "")}</strong>
      {warnings.length > 0 && <small className="warning">{warnings.join(", ")}</small>}
      <small>{blockLocation(block)} · {String(block.confidence ?? "")}</small>
      <p>{String(block.text ?? "")}</p>
      {context.length > 1 && (
        <div className="source-context">
          <small>{contextLabel(t)}</small>
          {context.map((item) => <span key={String(item.id)}>{String(item.text ?? "").slice(0, 180)}</span>)}
        </div>
      )}
    </div>
  );
}

function FieldNote({ item, t }: { item: unknown; t: Props["t"] }) {
  const note = objectValue(item);
  const source = objectValue(note.source);
  const location = source.block_id
    ? `${String(source.block_id).slice(0, 12)}${source.page ? ` · page ${String(source.page)}` : ""}`
    : "";
  return (
    <small className={`field-note ${String(note.status ?? "")}`}>
      {String(note.field ?? "")}: {t(String(note.status ?? ""))}
      {location ? ` · ${location}` : ""}
    </small>
  );
}

export function PreviewFieldNotes({ notes, t }: { notes: unknown[]; t: Props["t"] }) {
  if (notes.length === 0) return null;
  return <div className="field-note-grid">{notes.slice(0, 8).map((item, index) => <FieldNote item={item} key={index} t={t} />)}</div>;
}

function rowId(row: Record<string, unknown>) {
  return String(row.row_id || `${String(row.source_document_id ?? "")}:${String(row.source_block_id ?? "")}`);
}

function blockLocation(block: Record<string, unknown>) {
  if (block.page) return `page ${String(block.page)}`;
  if (block.sheet_name) return `sheet ${String(block.sheet_name)}`;
  if (block.slide_number) return `slide ${String(block.slide_number)}`;
  return "block";
}

function sourceLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "дереккөз";
  if (language === "Language") return "source";
  return "источник";
}

function closeLabel(t: Props["t"]) {
  return t("language") === "Language" ? "close" : "закрыть";
}

function contextLabel(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "контекст";
  if (language === "Language") return "context";
  return "контекст";
}

function evidenceRows(notes: unknown[]) {
  const seen = new Set<string>();
  return notes.flatMap((item) => {
    const note = objectValue(item);
    const source = objectValue(note.source);
    const evidence = String(source.evidence ?? "").trim();
    if (!evidence) return [];
    const key = `${String(note.field)}:${evidence}`;
    if (seen.has(key)) return [];
    seen.add(key);
    return [{ field: String(note.field ?? ""), location: blockLocation(source), evidence }];
  });
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function recordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item) => typeof item === "object") as Array<Record<string, unknown>> : [];
}
