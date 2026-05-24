import { CheckSquare, Square } from "lucide-react";
import type { DocumentFile } from "@shared/types";

type Props = {
  files: DocumentFile[];
  selectedIds: string[];
  onChange: (ids: string[]) => void;
  t: (key: string) => string;
};

export function LoadDocumentPicker({ files, selectedIds, onChange, t }: Props) {
  if (files.length === 0) return null;
  const selected = new Set(selectedIds);
  const allSelected = selected.size === files.length;
  function toggle(id: string) {
    const next = new Set(selected);
    if (next.has(id)) {
      next.delete(id);
    } else {
      next.add(id);
    }
    onChange([...next]);
  }
  return (
    <div className="document-picker">
      <div className="document-picker-head">
        <strong>{t("selectedDocuments")}: {selected.size}/{files.length}</strong>
        <button onClick={() => onChange(allSelected ? [] : files.map((file) => file.id))}>
          {allSelected ? t("clearSelection") : t("allDocuments")}
        </button>
      </div>
      <div className="document-picker-list">
        {files.map((file) => (
          <button className={selected.has(file.id) ? "active" : ""} key={file.id} onClick={() => toggle(file.id)}>
            {selected.has(file.id) ? <CheckSquare size={15} /> : <Square size={15} />}
            <span>{file.file_name}</span>
            <small>{file.status}</small>
          </button>
        ))}
      </div>
    </div>
  );
}
