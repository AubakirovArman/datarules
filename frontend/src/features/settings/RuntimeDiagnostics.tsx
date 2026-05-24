import { Activity, AlertTriangle, CheckCircle2, CircleSlash, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@shared/api";
import type { DiagnosticCheck, RuntimeDiagnostics as RuntimeDiagnosticsType } from "@shared/types";

type Props = {
  t: (key: string) => string;
};

export function RuntimeDiagnostics({ t }: Props) {
  const [value, setValue] = useState<RuntimeDiagnosticsType>();

  async function refresh() {
    setValue(await api.diagnostics());
  }

  useEffect(() => {
    void refresh();
  }, []);

  if (!value) return null;
  return (
    <div className={`runtime-diagnostics ${value.status}`}>
      <div className="diagnostics-head">
        <strong><Activity size={15} /> {t("runtimeDiagnostics")}</strong>
        <button className="icon-button" onClick={refresh} title={t("refresh")}>
          <RefreshCw size={14} />
        </button>
      </div>
      <div className="diagnostics-grid">
        {value.checks.map((check) => <CheckItem check={check} t={t} key={check.key} />)}
      </div>
    </div>
  );
}

function CheckItem({ check, t }: { check: DiagnosticCheck; t: Props["t"] }) {
  return (
    <div className={`diagnostic-check ${check.status}`}>
      {icon(check.status)}
      <div>
        <strong>{t(`diag_${check.key}`)}</strong>
        <small>{t(`diagStatus_${check.status}`)} · {check.latency_ms} ms</small>
        <code>{detailText(check)}</code>
      </div>
    </div>
  );
}

function icon(status: DiagnosticCheck["status"]) {
  if (status === "ok") return <CheckCircle2 size={15} />;
  if (status === "disabled") return <CircleSlash size={15} />;
  if (status === "warning") return <AlertTriangle size={15} />;
  return <AlertTriangle size={15} />;
}

function detailText(check: DiagnosticCheck) {
  const details = check.details || {};
  if (check.key === "database") return `extensions: ${arrayText(details.extensions)} missing: ${arrayText(details.missing)}`;
  if (check.key === "storage") return arrayText(details.paths);
  if (check.key === "ingestion_runner") return `active: ${String(details.active ?? 0)} stale: ${String(details.stale ?? 0)}`;
  if (check.key === "gemma") return [details.model, details.gpu_id ? `GPU ${details.gpu_id}` : ""].filter(Boolean).join(" · ");
  if (check.key === "embeddings") return [details.model, details.dimensions ? `${details.dimensions}d` : ""].filter(Boolean).join(" · ");
  if (check.key === "secret_storage") return String(details.status ?? "");
  return String(details.error ?? "");
}

function arrayText(value: unknown) {
  return Array.isArray(value) && value.length ? value.join(", ") : "-";
}
