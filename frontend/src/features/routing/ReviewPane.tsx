import { Check, RefreshCw, Route, Sparkles } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "@shared/api";
import type { DocumentReview, DocumentSummary, ReviewOption } from "@shared/types";

type Props = {
  datasetId?: string;
  reviews: DocumentReview[];
  summaries: DocumentSummary[];
  onRefresh: () => Promise<void>;
  onConfirm: (id: string, docType: string, table: string, notes: string) => Promise<void>;
  t: (key: string) => string;
};

export function ReviewPane({ datasetId, reviews, summaries, onRefresh, onConfirm, t }: Props) {
  const [accepting, setAccepting] = useState(false);
  const [error, setError] = useState("");
  const byDocument = useMemo(() => new Map(summaries.map((item) => [item.document_id, item])), [summaries]);
  const pending = reviews.filter((review) => review.status !== "confirmed");
  const confirmed = reviews.length - pending.length;

  async function acceptRecommended() {
    if (!datasetId) return;
    setAccepting(true);
    setError("");
    try {
      await api.acceptRecommendedReviews(datasetId);
      await onRefresh();
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err));
    } finally {
      setAccepting(false);
    }
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>{t("documentRouting")}</h2>
        <div className="review-actions">
          <span>{t("routesConfirmed")}: {confirmed}</span>
          <span>{t("routesPending")}: {pending.length}</span>
          <button disabled={accepting || pending.length === 0 || !datasetId} onClick={acceptRecommended}>
            <Sparkles size={16} />
            <span>{t("acceptRecommended")}</span>
          </button>
          <button className="icon-button" onClick={onRefresh} title={t("refresh")}>
            <RefreshCw size={16} />
          </button>
        </div>
      </div>
      {error && <div className="error-banner">{error}</div>}
      <div className="review-list">
        {reviews.map((review) => (
          <ReviewCard
            key={review.id}
            review={review}
            summary={byDocument.get(review.document_id)}
            onConfirm={onConfirm}
            t={t}
          />
        ))}
        {reviews.length === 0 && <div className="empty">{t("noReviews")}</div>}
      </div>
    </section>
  );
}

function ReviewCard({
  review,
  summary,
  onConfirm,
  t,
}: {
  review: DocumentReview;
  summary?: DocumentSummary;
  onConfirm: Props["onConfirm"];
  t: Props["t"];
}) {
  const [docType, setDocType] = useState(
    review.selected_doc_type ?? review.doc_type_options[0]?.value ?? "",
  );
  const [table, setTable] = useState(review.selected_table ?? review.table_options[0]?.value ?? "");
  const [notes, setNotes] = useState(review.notes ?? "");
  const [busy, setBusy] = useState(false);
  const docOption = review.doc_type_options.find((option) => option.value === docType);
  const tableOption = review.table_options.find((option) => option.value === table);

  useEffect(() => {
    setDocType(review.selected_doc_type ?? review.doc_type_options[0]?.value ?? "");
    setTable(review.selected_table ?? review.table_options[0]?.value ?? "");
    setNotes(review.notes ?? "");
  }, [review]);

  async function submit() {
    setBusy(true);
    try {
      await onConfirm(review.id, docType, table, notes);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="review-card">
      <div className="review-head">
        <Route size={16} />
        <strong>{review.file_name ?? review.document_id}</strong>
        <span className={`status ${review.status}`}>{review.status}</span>
      </div>
      <small>{review.reason}</small>
      {summary && <RouteSummary summary={summary} t={t} />}
      <div className="route-pair">
        <span>{t("recommendedPair")}</span>
        <strong>{docOption?.label ?? docType} → {tableOption?.label ?? table}</strong>
      </div>
      <label>
        <span>{t("docKind")}</span>
        <select value={docType} onChange={(event) => setDocType(event.target.value)}>
          {review.doc_type_options.map((option) => (
            <option value={option.value} key={option.value}>
              {option.label} · {t("confidence")} {Math.round(option.confidence * 100)}%
            </option>
          ))}
        </select>
      </label>
      <OptionInsight option={docOption} t={t} />
      <label>
        <span>{t("targetTable")}</span>
        <select value={table} onChange={(event) => setTable(event.target.value)}>
          {review.table_options.map((option) => (
            <option value={option.value} key={option.value}>
              {option.label} · {Math.round(option.confidence * 100)}%
            </option>
          ))}
        </select>
      </label>
      <OptionInsight option={tableOption} t={t} />
      <input value={notes} onChange={(event) => setNotes(event.target.value)} placeholder={t("notes")} />
      <button disabled={busy || !docType || !table} onClick={submit}>
        <Check size={16} />
        <span>{t("confirmChoice")}</span>
      </button>
    </div>
  );
}

function RouteSummary({ summary, t }: { summary: DocumentSummary; t: Props["t"] }) {
  return (
    <div className="route-summary">
      <strong>{t("routeSummary")}</strong>
      <p>{summary.summary}</p>
      <div className="route-summary-metrics">
        <span>{t("pages")}: {summary.pages}</span>
        <span>{t("tables")}: {summary.tables}</span>
        <span>{t("routingQuality")}: {summary.quality_profile.extraction_score}%</span>
      </div>
    </div>
  );
}

function OptionInsight({ option, t }: { option?: ReviewOption; t: Props["t"] }) {
  if (!option) return null;
  return (
    <div className="route-insight">
      <span>{t("routeSource")}: {option.source ?? "router"}</span>
      {option.reason && <p>{t("routeReason")}: {option.reason}</p>}
      {option.signals && option.signals.length > 0 && (
        <small>{t("routeSignals")}: {option.signals.slice(0, 8).join(", ")}</small>
      )}
      {option.evidence && option.evidence.length > 0 && (
        <div className="route-evidence">
          <strong>{t("evidence")}</strong>
          {option.evidence.slice(0, 3).map((item, index) => <em key={index}>{item}</em>)}
        </div>
      )}
    </div>
  );
}
