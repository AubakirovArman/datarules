import { FileUp, Play, RefreshCw, Trash2 } from "lucide-react";
import { ChangeEvent, useRef, useState } from "react";
import type { DocumentFile, Job } from "@shared/types";

type Props = {
  disabled: boolean;
  files: DocumentFile[];
  onUpload: (files: FileList) => Promise<void>;
  onDelete: (documentId: string) => Promise<void>;
  onRefresh: () => Promise<void>;
  onStart: () => Promise<Job | undefined>;
  t: (key: string) => string;
};

export function UploadPane({ disabled, files, onUpload, onDelete, onRefresh, onStart, t }: Props) {
  const inputRef = useRef<HTMLInputElement | null>(null);
  const [busy, setBusy] = useState(false);

  async function uploadFiles(list: FileList | null) {
    if (disabled) return;
    if (!list?.length) return;
    setBusy(true);
    try {
      await onUpload(list);
    } finally {
      setBusy(false);
    }
  }

  async function handleFiles(event: ChangeEvent<HTMLInputElement>) {
    try {
      await uploadFiles(event.target.files);
    } finally {
      event.target.value = "";
    }
  }

  async function start() {
    setBusy(true);
    try {
      await onStart();
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>{t("files")}</h2>
        <div className="toolbar">
          <button className="icon-button" onClick={onRefresh} title={t("refresh")} disabled={disabled}>
            <RefreshCw size={16} />
          </button>
          <button onClick={() => inputRef.current?.click()} disabled={disabled || busy}>
            <FileUp size={16} />
            <span>{t("upload")}</span>
          </button>
          <button onClick={start} disabled={disabled || busy || files.length === 0}>
            <Play size={16} />
            <span>{t("analyze")}</span>
          </button>
        </div>
      </div>
      <input
        ref={inputRef}
        className="hidden"
        type="file"
        multiple
        accept=".pdf,.csv,.xlsx,.xlsm,.xls,.docx,.doc,.pptx,.ppt,.txt,.md,.html,.htm,.json,.xml"
        onChange={handleFiles}
      />
      <div
        className={disabled ? "upload-zone disabled" : "upload-zone"}
        role="button"
        tabIndex={disabled ? -1 : 0}
        onClick={() => !disabled && inputRef.current?.click()}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          void uploadFiles(event.dataTransfer.files);
        }}
        onKeyDown={(event) => {
          if (event.key === "Enter" || event.key === " ") inputRef.current?.click();
        }}
      >
        <FileUp size={28} />
        <strong>{t("upload")}</strong>
        <span>{t("actionUploadDetail")}</span>
      </div>
      <div className="file-table">
        <div className="table-head">
          <span>{t("name")}</span>
          <span>{t("type")}</span>
          <span>{t("status")}</span>
        </div>
        {files.map((file) => (
          <div className="table-row" key={file.id}>
            <span title={file.file_name}>{file.file_name}</span>
            <span>{file.file_type}</span>
            <span className="row-actions">
              {file.status}
              <button
                className="icon-button danger"
                disabled={disabled || busy}
                onClick={() => onDelete(file.id)}
                title={t("delete")}
              >
                <Trash2 size={15} />
              </button>
            </span>
          </div>
        ))}
        {files.length === 0 && <div className="empty">{t("noFiles")}</div>}
      </div>
    </section>
  );
}
