import { DatabaseZap, Download, GitCompareArrows, PlayCircle, RefreshCw } from "lucide-react";
import { useState } from "react";
import { api } from "@shared/api";
import type { LoadPlan } from "@shared/types";
import { LoadPreviewDiff } from "./LoadPreviewDiff";

type Props = {
  plan: LoadPlan;
  preflightBlocked: boolean;
  dirty: boolean;
  onConfirm: (planId: string) => Promise<void>;
  onPlanUpdated: (plan: LoadPlan) => void;
  t: (key: string) => string;
};

export function LoadPlanActions({ plan, preflightBlocked, dirty, onConfirm, onPlanUpdated, t }: Props) {
  const [busy, setBusy] = useState("");
  const [showDiff, setShowDiff] = useState(false);
  const [error, setError] = useState("");
  return (
    <>
      {error && <small className="load-save-warning">{error}</small>}
      <div className="load-actions">
        <button disabled={preflightBlocked || plan.status !== "needs_confirmation" || dirty} onClick={() => onConfirm(plan.id)}>
          <DatabaseZap size={16} />
          <span>{plan.target_mode === "analysis_only" ? t("indexForAgent") : t("loadData")}</span>
        </button>
        <button disabled={plan.status === "loaded" || busy === "rebuild" || dirty} onClick={() => void run("rebuild", plan.id, setBusy, setError, onPlanUpdated)}>
          <PlayCircle size={16} />
          <span>{t("buildPreview")}</span>
        </button>
        <button disabled={dirty || plan.preview_rows.length === 0} onClick={() => setShowDiff(!showDiff)}>
          <GitCompareArrows size={16} />
          <span>{diffText(t)}</span>
        </button>
        <button disabled={plan.status !== "loaded" || busy === "reindex"} onClick={() => void run("reindex", plan.id, setBusy, setError, onPlanUpdated)}>
          <RefreshCw size={16} />
          <span>{reindexText(t)}</span>
        </button>
        <button disabled={plan.status !== "loaded"} onClick={() => exportPlan(plan.id, "csv")}>
          <Download size={16} />
          <span>{t("exportCsv")}</span>
        </button>
        <button disabled={plan.status !== "loaded"} onClick={() => exportPlan(plan.id, "json")}>
          <Download size={16} />
          <span>{t("exportJson")}</span>
        </button>
      </div>
      {showDiff && <LoadPreviewDiff planId={plan.id} onClose={() => setShowDiff(false)} t={t} />}
    </>
  );
}

async function run(action: "rebuild" | "reindex", planId: string, setBusy: (value: string) => void, setError: (value: string) => void, onPlanUpdated: (plan: LoadPlan) => void) {
  setBusy(action);
  setError("");
  try {
    onPlanUpdated(action === "rebuild" ? await api.rebuildLoadPlan(planId) : await api.reindexLoadPlan(planId));
  } catch (error) {
    setError(error instanceof Error ? error.message : String(error));
  } finally {
    setBusy("");
  }
}

function exportPlan(planId: string, format: "csv" | "json") {
  window.open(`/api/load-plans/${planId}/export.${format}`, "_blank", "noopener,noreferrer");
}

function reindexText(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "Қайта индекстеу";
  if (language === "Language") return "Reindex agent";
  return "Переиндексировать";
}

function diffText(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "Preview салыстыру";
  if (language === "Language") return "Preview diff";
  return "Сравнить preview";
}
