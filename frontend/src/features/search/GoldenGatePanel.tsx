import { useEffect, useState } from "react";
import { api } from "@shared/api";

type Props = {
  datasetId?: string;
  refreshKey: string;
  t: (key: string) => string;
};

export function GoldenGatePanel({ datasetId, refreshKey, t }: Props) {
  const [gate, setGate] = useState<Record<string, unknown>>();

  useEffect(() => {
    if (!datasetId) return;
    api.goldenGate(datasetId).then(setGate).catch(() => setGate(undefined));
  }, [datasetId, refreshKey]);

  if (!gate) return null;
  const latest = objectValue(gate.latest_run);
  const thresholds = objectValue(gate.thresholds);
  return (
    <span className={`history-row ${gate.pass ? "ready" : "warning"}`}>
      <b>{label(t)} · {String(gate.status)}</b>
      score {String(latest.score ?? "-")} / {String(thresholds.min_score ?? "-")}
      {reasons(gate).length ? ` · ${reasons(gate).join(", ")}` : ""}
      <small>{String(latest.created_at ?? "")}</small>
    </span>
  );
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function reasons(gate: Record<string, unknown>) {
  return Array.isArray(gate.reasons) ? gate.reasons.map(String) : [];
}

function label(t: Props["t"]) {
  if (t("language") === "Язык") return "Golden gate";
  if (t("language") === "Тіл") return "Golden gate";
  return "Golden gate";
}
