import { Activity, AlertTriangle, CheckCircle2, StopCircle } from "lucide-react";
import { useState } from "react";
import { api } from "@shared/api";
import type { Job, JobEvent } from "@shared/types";

type Props = {
  job?: Job;
  events: JobEvent[];
  t: (key: string) => string;
};

export function JobProgress({ job, events, t }: Props) {
  const latest = events.at(-1);
  const progress = latest?.progress_percent ?? 0;
  const [busy, setBusy] = useState(false);
  const cancellable = job ? ["queued", "running", "cancelling"].includes(job.status) : false;

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>{t("ingestion")}</h2>
        <div className="toolbar">
          {cancellable && (
            <button className="icon-button danger" disabled={busy || job?.status === "cancelling"} onClick={() => void cancel(job, setBusy, t)} title={cancelText(t)}>
              <StopCircle size={15} />
            </button>
          )}
          <span className={`status ${job?.status ?? "idle"}`}>{job?.status ?? "idle"}</span>
        </div>
      </div>
      <div className="progress-line">
        <div style={{ width: `${progress}%` }} />
      </div>
      <div className="job-meta">
        <span>{job?.current_stage ?? "queued"}</span>
        <span>{progress}%</span>
        <span>
          {job?.processed_files ?? 0}/{job?.total_files ?? 0} files
        </span>
        <span>
          attempt {job?.attempt_count ?? 0}/{job?.max_attempts ?? 3}
        </span>
      </div>
      <div className="events">
        {events.slice(-8).map((event) => (
          <div className="event-row" key={event.id}>
            {event.stage === "failed" ? (
              <AlertTriangle size={15} />
            ) : event.progress_percent === 100 ? (
              <CheckCircle2 size={15} />
            ) : (
              <Activity size={15} />
            )}
            <span>{event.message}</span>
            <small>{event.stage}</small>
          </div>
        ))}
        {events.length === 0 && <div className="empty">{t("noJob")}</div>}
      </div>
    </section>
  );
}

async function cancel(job: Job | undefined, setBusy: (value: boolean) => void, t: Props["t"]) {
  if (!job || !window.confirm(confirmText(t))) return;
  setBusy(true);
  try {
    await api.cancelJob(job.id);
  } finally {
    setBusy(false);
  }
}

function cancelText(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "Тоқтату";
  if (language === "Language") return "Cancel";
  return "Остановить";
}

function confirmText(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "Талдауды тоқтату керек пе?";
  if (language === "Language") return "Cancel document analysis?";
  return "Остановить анализ документов?";
}
