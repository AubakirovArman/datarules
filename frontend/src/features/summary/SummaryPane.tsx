import { FileText, Layers, RefreshCw } from "lucide-react";
import type { DocumentSummary } from "@shared/types";
import { DocumentQualityPanel } from "./DocumentQualityPanel";
import { destinationItems, formatPageLabel, formatQualityWarning, summaryItems, summaryText } from "./summaryFormatting";

type Props = {
  datasetId?: string;
  summaries: DocumentSummary[];
  onRefresh: () => Promise<void>;
  t: (key: string) => string;
};

export function SummaryPane({ datasetId, summaries, onRefresh, t }: Props) {
  return (
    <section className="panel summary-panel">
      <div className="panel-head">
        <h2>{t("documentSummary")}</h2>
        <button className="icon-button" onClick={onRefresh} title={t("refresh")}>
          <RefreshCw size={16} />
        </button>
      </div>
      <DocumentQualityPanel datasetId={datasetId} refreshKey={summaries.map((item) => `${item.document_id}:${item.status}`).join("|")} onRepair={onRefresh} t={t} />
      <div className="summary-list">
        {summaries.map((summary) => (
          <article className="summary-card" key={summary.document_id}>
            <div className="summary-title">
              <FileText size={17} />
              <strong>{summary.file_name}</strong>
              <small>{summary.status} · {summary.summary_source}</small>
              {datasetId && (
                <a
                  className="icon-button"
                  href={`/api/datasets/${datasetId}/files/${summary.document_id}/canonical`}
                  target="_blank"
                  rel="noreferrer"
                >
                  {t("exportJson")}
                </a>
              )}
            </div>
            <div className="ai-summary-label">{t("gemmaSummary")}</div>
            <p>{summaryText(summary.summary, summary.ai_summary.summary)}</p>
            <SummaryList title={t("keyPoints")} value={summary.ai_summary.key_points} />
            <SummaryList title={t("entities")} value={summary.ai_summary.entities} />
            <SummaryList
              title={t("recommendedDestinations")}
              value={destinationItems(summary.ai_summary.table_candidates ?? summary.ai_summary.recommended_destinations)}
            />
            <SummaryList title={t("qualityNotes")} value={summary.ai_summary.quality_notes} />
            <QualityProfile value={summary.quality_profile} t={t} />
            <div className="metric-row">
              <Metric label={t("pages")} value={summary.pages} />
              <Metric label={t("sheets")} value={summary.sheets.length} />
              <Metric label={t("slides")} value={summary.slides} />
              <Metric label={t("tables")} value={summary.tables} />
            </div>
            <div className="page-list">
              {summary.page_summaries.slice(0, 8).map((page) => (
                <span key={page.label}>
                  <Layers size={13} />
                  {formatPageLabel(page.label, t)}: {page.blocks} {t("blocks")}
                  {page.low_confidence_blocks ? ` · ${t("lowConfidence")} ${page.low_confidence_blocks}` : ""}
                  {page.semantic_summary ? ` · ${t("pageMeaning")}: ${page.semantic_summary}` : ""}
                </span>
              ))}
            </div>
          </article>
        ))}
        {summaries.length === 0 && <div className="empty">{t("noSummaries")}</div>}
      </div>
    </section>
  );
}

function QualityProfile({ value, t }: { value?: Record<string, unknown>; t: (key: string) => string }) {
  if (!value) return null;
  const warnings = Array.isArray(value.warnings) ? value.warnings : [];
  return (
    <>
      <div className="metric-row">
        <Metric label={t("confidence")} value={`${value.extraction_score ?? 0}%`} />
        <Metric label={t("lowConfidence")} value={Number(value.low_confidence_blocks ?? 0)} />
        <Metric label={t("validation")} value={String(value.status ?? "")} />
      </div>
      <SummaryList title={t("validation")} value={warnings.map((item) => formatQualityWarning(item, t))} />
    </>
  );
}

function SummaryList({ title, value }: { title: string; value: unknown }) {
  const items = summaryItems(value);
  if (items.length === 0) return null;
  return (
    <div className="ai-summary-list">
      <strong>{title}</strong>
      {items.map((item, index) => <span key={index}>{item}</span>)}
    </div>
  );
}

function Metric({ label, value }: { label: string; value: number | string }) {
  return (
    <div className="metric">
      <strong>{value}</strong>
      <span>{label}</span>
    </div>
  );
}
