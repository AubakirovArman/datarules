import { Search } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { api } from "@shared/api";
import type { AnswerHistory, AskResponse, SearchHit } from "@shared/types";
import { GoldenChecksPanel } from "./GoldenChecksPanel";
import { QueryGuide } from "./QueryGuide";
import { StructuredSqlPane } from "./StructuredSqlPane";

type Props = {
  datasetId?: string;
  disabled: boolean;
  onSearch: (query: string) => Promise<SearchHit[]>;
  onAsk: (query: string) => Promise<AskResponse>;
  t: (key: string) => string;
};

type SearchMode = "ask" | "expert" | "debug";

export function SearchPane({ datasetId, disabled, onSearch, onAsk, t }: Props) {
  const [mode, setMode] = useState<SearchMode>("ask");
  const [query, setQuery] = useState("");
  const [hits, setHits] = useState<SearchHit[]>([]);
  const [answer, setAnswer] = useState<AskResponse | undefined>();
  const [history, setHistory] = useState<AnswerHistory[]>([]);
  const [golden, setGolden] = useState<Array<Record<string, unknown>>>([]);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    if (!datasetId) return;
    api.answerHistory(datasetId).then(setHistory).catch(() => setHistory([]));
    api.goldenChecks(datasetId).then(setGolden).catch(() => setGolden([]));
  }, [datasetId]);

  async function submit(event: FormEvent, mode: "search" | "ask" = "search") {
    event.preventDefault();
    setBusy(true);
    try {
      if (mode === "ask") {
        const next = await onAsk(query);
        setAnswer(next);
        setHits(next.citations.map(citationToHit));
        if (datasetId) setHistory(await api.answerHistory(datasetId));
      } else {
        setAnswer(undefined);
        setHits(await onSearch(query));
      }
    } finally {
      setBusy(false);
    }
  }

  async function replay(answerId: string) {
    if (!datasetId) return;
    setBusy(true);
    try {
      const next = await api.replayAnswer(answerId);
      setAnswer(next);
      setHits(next.citations.map(citationToHit));
      setHistory(await api.answerHistory(datasetId));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel search-panel">
      <div className="panel-head">
        <h2>{t("search")}</h2>
      </div>
      <div className="segmented">
        <button className={mode === "ask" ? "active" : ""} onClick={() => setMode("ask")} type="button">{t("askAgent")}</button>
        <button className={mode === "expert" ? "active" : ""} onClick={() => setMode("expert")} type="button">{t("structuredSql")}</button>
        <button className={mode === "debug" ? "active" : ""} onClick={() => setMode("debug")} type="button">Debug</button>
      </div>
      {mode !== "debug" && <QueryGuide datasetId={datasetId} t={t} />}
      {(mode === "expert" || mode === "debug") && <StructuredSqlPane datasetId={datasetId} disabled={disabled} t={t} />}
      {mode === "debug" && <GoldenChecksPanel datasetId={datasetId} checks={golden} disabled={disabled || busy} onChange={setGolden} t={t} />}
      <form className="search-form" onSubmit={(event) => submit(event, mode === "ask" ? "ask" : "search")}>
        <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder={t("searchPlaceholder")} />
        <button disabled={disabled || busy || !query.trim()} type="submit">
          <Search size={16} />
          <span>{mode === "ask" ? t("askAgent") : t("search")}</span>
        </button>
        {mode !== "ask" && (
          <button disabled={disabled || busy || !query.trim()} onClick={(event) => submit(event, "ask")} type="button">
            <Search size={16} />
            <span>{t("askAgent")}</span>
          </button>
        )}
        {mode === "ask" && (
          <button disabled={disabled || busy || !query.trim()} onClick={(event) => submit(event, "search")} type="button">
          <Search size={16} />
            <span>{t("search")}</span>
          </button>
        )}
      </form>
      {answer && (
        <div className="ai-summary-list">
          <strong>{t("answer")} · {answer.confidence} · {answer.model_source} · {answer.prompt_version}</strong>
          <span>{answer.answer}</span>
          {mode === "debug" && <GroundingTrace value={answer.grounding} t={t} />}
        </div>
      )}
      {mode !== "expert" && history.length > 0 && (
        <div className="ai-summary-list">
          <strong>{t("answerHistory")}</strong>
          {history.slice(0, 5).map((item) => <HistoryRow item={item} onReplay={replay} t={t} key={item.id} />)}
        </div>
      )}
      <div className="search-results">
        {hits.map((hit) => (
          <div className="hit" key={hit.block_id}>
            <div>
              <strong>{hit.file_name}</strong>
              <small>
                {hit.match_source ?? hit.block_type}
                {hit.target_table ? ` · ${hit.target_table}` : ""}
                {hit.page ? ` · page ${hit.page}` : ""}
                {hit.sheet_name ? ` · ${hit.sheet_name}` : ""}
                {` · ${hit.score.toFixed(2)}`}
              </small>
            </div>
            <p>{hit.text || "No text in block."}</p>
            {typeof hit.metadata?.embedding_status === "string" && (
              mode === "debug" && <code>{`embedding: ${String(hit.metadata.embedding_status)}`}</code>
            )}
            {mode === "debug" && <FusionTrace value={hit.metadata?.fusion} />}
            {mode === "debug" && <RerankTrace value={hit.metadata?.rerank} />}
          </div>
        ))}
        {hits.length === 0 && <div className="empty">{t("noResults")}</div>}
      </div>
    </section>
  );
}

function GroundingTrace({ value, t }: { value: unknown; t: Props["t"] }) {
  if (!value || typeof value !== "object") return null;
  const grounding = value as Record<string, unknown>;
  const markers = Array.isArray(grounding.valid_markers) ? grounding.valid_markers.join(" ") : "";
  const gate = objectValue(grounding.quality_gate);
  const reasons = Array.isArray(gate.reasons) ? gate.reasons.map(String).join(", ") : "";
  const gateText = Object.keys(gate).length ? ` · gate ${String(gate.status ?? "")}${reasons ? `: ${reasons}` : ""}` : "";
  return <code>{`${t("evidence")}: ${String(grounding.status ?? "")} · ${markers} · coverage ${String(grounding.coverage ?? 0)}${gateText}`}</code>;
}

function RerankTrace({ value }: { value: unknown }) {
  if (!value || typeof value !== "object") return null;
  const rerank = value as Record<string, unknown>;
  const terms = Array.isArray(rerank.matched_terms) ? rerank.matched_terms.map(String).join(", ") : "";
  const score = `${String(rerank.score_before ?? "")}->${String(rerank.score_after ?? "")}`;
  return <code>{`rerank: ${String(rerank.method ?? "")} · ${terms || "no term match"} · p=${String(rerank.provenance_score ?? 0)} · ${score}`}</code>;
}

function FusionTrace({ value }: { value: unknown }) {
  if (!value || typeof value !== "object") return null;
  const fusion = value as Record<string, unknown>;
  const sources = Array.isArray(fusion.sources) ? fusion.sources.map(String).join(" + ") : "";
  const ranks = formatRanks(fusion.source_ranks);
  return <code>{`fusion: ${String(fusion.method ?? "rrf")} ${sources}${ranks ? ` · ${ranks}` : ""}`}</code>;
}

function formatRanks(value: unknown) {
  if (!value || typeof value !== "object") return "";
  return Object.entries(value as Record<string, unknown>)
    .map(([source, rank]) => `${source}#${String(rank)}`)
    .join(" ");
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function HistoryRow({ item, onReplay, t }: { item: AnswerHistory; onReplay: (id: string) => void; t: Props["t"] }) {
  return (
    <span className="history-row">
      {item.query} · {item.confidence} · {item.model_source} · {item.prompt_version}
      {item.replay_of_answer_id ? ` · replay ${item.replay_of_answer_id}` : ""}
      <button onClick={() => onReplay(item.id)} type="button">{t("replay")}</button>
      <GroundingTrace value={item.grounding_json} t={t} />
    </span>
  );
}

function citationToHit(citation: AskResponse["citations"][number]): SearchHit {
  return {
    document_id: citation.document_id,
    block_id: citation.block_id,
    file_name: citation.file_name,
    block_type: citation.block_type ?? "citation",
    page: citation.page,
    sheet_name: citation.sheet_name,
    text: `${citation.marker} ${citation.text}`,
    score: citation.score,
    target_table: citation.target_table,
    match_source: citation.match_source ?? "citation",
    metadata: citation.metadata ?? {},
  };
}
