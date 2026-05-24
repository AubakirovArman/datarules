import { Compass, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@shared/api";

type Props = {
  datasetId?: string;
  t: (key: string) => string;
};

export function QueryGuide({ datasetId, t }: Props) {
  const [guide, setGuide] = useState<Record<string, unknown>>();
  const [busy, setBusy] = useState(false);
  const language = languageValue();

  async function refresh() {
    if (!datasetId) return;
    setBusy(true);
    try {
      setGuide(await api.queryGuide(datasetId, language));
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, [datasetId, language]);

  if (!datasetId || !guide) return null;
  const tables = recordArray(guide.tables);
  const fields = recordArray(guide.fields);
  const filters = recordArray(guide.filters);
  const modes = recordArray(guide.search_modes);
  const examples = recordArray(guide.examples);
  return (
    <div className="query-guide">
      <div className="load-report-head">
        <strong><Compass size={15} /> {t("queryGuide")}</strong>
        <button className="icon-button" disabled={busy} onClick={refresh} title={t("refresh")}>
          <RefreshCw size={14} />
        </button>
      </div>
      <small>{t("status")}: {t(String(guide.status ?? ""))}</small>
      <GuideList title={t("searchModes")} items={modes.map(modeText)} />
      <GuideList title={t("knownTables")} items={tables.map(tableText).slice(0, 6)} />
      <GuideList title={t("fields")} items={fields.map(fieldText).slice(0, 12)} />
      <GuideList title={t("availableFilters")} items={filters.map((item) => String(item.name)).slice(0, 10)} />
      <GuideList title={t("queryExamples")} items={examples.map((item) => `${String(item.mode)}: ${String(item.question)}`)} />
    </div>
  );
}

function GuideList({ title, items }: { title: string; items: string[] }) {
  if (items.length === 0) return null;
  return (
    <div className="ai-summary-list">
      <strong>{title}</strong>
      {items.map((item, index) => <span key={index}>{item}</span>)}
    </div>
  );
}

function tableText(item: Record<string, unknown>) {
  const state = item.ready_for_agent ? "agent" : String(item.status ?? "");
  return `${String(item.schema ?? "public")}.${String(item.table)} · ${state} · ${String(item.loaded_rows ?? item.rows ?? 0)}`;
}

function fieldText(item: Record<string, unknown>) {
  const tables = Array.isArray(item.tables) ? item.tables.slice(0, 3).join(", ") : "";
  return `${String(item.name)} · ${String(item.type ?? "text")}${tables ? ` · ${tables}` : ""}`;
}

function modeText(item: Record<string, unknown>) {
  return `${String(item.mode)} · ${item.ready ? "OK" : "ATTN"} · ${String(item.scope ?? "")}`;
}

function recordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item) => typeof item === "object") as Array<Record<string, unknown>> : [];
}

function languageValue() {
  const value = localStorage.getItem("datarules-language") || "ru";
  return ["ru", "kk", "en"].includes(value) ? value : "ru";
}
