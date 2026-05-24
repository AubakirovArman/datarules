import { AlertTriangle, CheckCircle2, CircleDashed } from "lucide-react";
import type { DocumentReview } from "@shared/types";

type Props = {
  documentIds: string[];
  reviews: DocumentReview[];
  schemaVersionId: string;
  schemaVersions: Array<Record<string, unknown>>;
  table: string;
  t: (key: string) => string;
};

export function LoadPreflight({ documentIds, reviews, schemaVersionId, schemaVersions, table, t }: Props) {
  const confirmed = reviews.filter((review) => review.status === "confirmed").length;
  const total = reviews.length;
  const selectedVersion = schemaVersions.find((version) => String(version.id) === schemaVersionId);
  const checks = [
    {
      key: "preflightDocuments",
      ok: documentIds.length > 0,
      attention: false,
      detail: `${documentIds.length} ${t("files")}`,
    },
    {
      key: "preflightRoutes",
      ok: total === 0 || confirmed === total,
      attention: total > 0 && confirmed > 0,
      detail: `${confirmed}/${total}`,
    },
    {
      key: "preflightSchema",
      ok: Boolean(selectedVersion),
      attention: schemaVersions.length > 0,
      detail: selectedVersion ? versionLabel(selectedVersion) : t("schemaVersionNone"),
    },
    {
      key: "preflightTarget",
      ok: Boolean(table.trim()),
      attention: false,
      detail: table || t("targetName"),
    },
  ];
  return (
    <div className="load-preflight">
      <strong>{t("loadPreflight")}</strong>
      <div>
        {checks.map((check) => (
          <span className={checkClass(check)} key={check.key}>
            {checkIcon(check)}
            <small>{t(check.key)}</small>
            <b>{check.detail}</b>
          </span>
        ))}
      </div>
    </div>
  );
}

function checkClass(check: { ok: boolean; attention: boolean }) {
  if (check.ok) return "ok";
  return check.attention ? "attention" : "blocked";
}

function checkIcon(check: { ok: boolean; attention: boolean }) {
  if (check.ok) return <CheckCircle2 size={14} />;
  if (check.attention) return <CircleDashed size={14} />;
  return <AlertTriangle size={14} />;
}

function versionLabel(version: Record<string, unknown>) {
  return `v${String(version.version ?? "")} · ${String(version.status ?? "")}`;
}
