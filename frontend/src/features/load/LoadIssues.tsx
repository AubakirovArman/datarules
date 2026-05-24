import type { LoadPlan } from "@shared/types";

type Props = {
  issues: LoadPlan["validation_issues"];
  t: (key: string) => string;
};

export function LoadIssues({ issues, t }: Props) {
  return (
    <div className="issue-list">
      <strong>{t("validation")}</strong>
      {issues.length === 0 && <span className="ok">OK</span>}
      {issues.map((issue, index) => (
        <span className={String(issue.severity)} key={index}>
          <strong>{issueText(issue, t)}</strong>
          {issueHint(issue, t) && <small>{issueHint(issue, t)}</small>}
        </span>
      ))}
    </div>
  );
}

function issueText(issue: Record<string, unknown>, t: Props["t"]) {
  const code = String(issue.code ?? "");
  const count = issue.count ? ` ${String(issue.count)}` : "";
  if (code === "source_repaired") return `${sourceRepairedText(t)}${count}`;
  return code ? `${t(code)}${count}` : String(issue.message ?? "");
}

function issueHint(issue: Record<string, unknown>, t: Props["t"]) {
  const code = String(issue.code ?? "");
  if (code === "unconfirmed_routes") return t("confirmRoutesBeforeLoad");
  if (code === "materialization_failed") return String(issue.message ?? "");
  if (code === "route_target_mismatch") return t("confirmRoutesBeforeLoad");
  if (code === "source_repaired") return String(issue.message ?? "");
  return "";
}

function sourceRepairedText(t: Props["t"]) {
  const language = t("language");
  if (language === "Тіл") return "Дереккөз қайта шығарылды";
  if (language === "Language") return "Source was re-extracted";
  return "Источник переизвлечён";
}
