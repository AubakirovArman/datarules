import { FormEvent, useEffect, useState } from "react";
import { api } from "@shared/api";
import { GoldenGatePanel } from "./GoldenGatePanel";

type Props = {
  datasetId?: string;
  checks: Array<Record<string, unknown>>;
  disabled: boolean;
  onChange: (checks: Array<Record<string, unknown>>) => void;
  t: (key: string) => string;
};

export function GoldenChecksPanel({ datasetId, checks, disabled, onChange, t }: Props) {
  const [question, setQuestion] = useState("");
  const [terms, setTerms] = useState("");
  const [profileText, setProfileText] = useState("");
  const [profileName, setProfileName] = useState("Investment projects");
  const [profileDomain, setProfileDomain] = useState("investment_projects");
  const [profiles, setProfiles] = useState<Array<Record<string, unknown>>>([]);
  const [runs, setRuns] = useState<Array<Record<string, unknown>>>([]);
  const [selectedProfile, setSelectedProfile] = useState("");
  const [status, setStatus] = useState("");

  useEffect(() => {
    api.goldenProfiles().then((rows) => {
      setProfiles(rows);
      setSelectedProfile((value) => value || String(rows[0]?.id ?? ""));
    }).catch(() => setProfiles([]));
    if (datasetId) api.goldenRuns(datasetId).then(setRuns).catch(() => setRuns([]));
  }, [datasetId]);

  async function create(event: FormEvent) {
    event.preventDefault();
    if (!datasetId || !question.trim()) return;
    await api.createGoldenCheck(datasetId, question, terms);
    onChange(await api.goldenChecks(datasetId));
    setQuestion("");
    setTerms("");
  }

  async function run() {
    if (!datasetId) return;
    const result = await api.runGoldenChecks(datasetId);
    onChange(recordArray(result.checks));
    setRuns(await api.goldenRuns(datasetId));
  }

  async function remove(id: string) {
    if (!datasetId) return;
    await api.deleteGoldenCheck(id);
    onChange(await api.goldenChecks(datasetId));
  }

  async function exportProfile() {
    if (!datasetId) return;
    const profile = await api.exportGoldenChecks(datasetId);
    setProfileText(JSON.stringify(profile, null, 2));
    downloadProfile(profile);
  }

  async function importProfile() {
    if (!datasetId || !profileText.trim()) return;
    try {
      const result = await api.importGoldenChecks(datasetId, JSON.parse(profileText));
      onChange(await api.goldenChecks(datasetId));
      setStatus(`${importedLabel(t)}: ${String(result.imported ?? 0)}`);
    } catch (error) {
      setStatus(error instanceof Error ? error.message : "Import failed");
    }
  }

  async function saveReusableProfile() {
    if (!datasetId || !checks.length) return;
    const profile = await api.saveGoldenProfile(datasetId, profileName, profileDomain);
    const rows = await api.goldenProfiles();
    setProfiles(rows);
    setSelectedProfile(String(profile.id ?? ""));
    setStatus(`${savedLabel(t)}: ${String(profile.name ?? "")} v${String(profile.version ?? "")}`);
  }

  async function applyReusableProfile() {
    if (!datasetId || !selectedProfile) return;
    const result = await api.applyGoldenProfile(datasetId, selectedProfile, false);
    onChange(await api.goldenChecks(datasetId));
    setStatus(`${importedLabel(t)}: ${String(result.imported ?? 0)}`);
  }

  return (
    <div className="ai-summary-list">
      <strong>{goldenLabel(t)}</strong>
      <form className="search-form" onSubmit={create}>
        <input value={question} onChange={(event) => setQuestion(event.target.value)} placeholder={questionLabel(t)} />
        <input value={terms} onChange={(event) => setTerms(event.target.value)} placeholder={termsLabel(t)} />
        <button disabled={disabled || !question.trim()} type="submit"><span>{t("savePreview")}</span></button>
        <button disabled={disabled || !checks.length} onClick={run} type="button"><span>{t("replay")}</span></button>
      </form>
      <div className="search-form">
        <button disabled={disabled || !checks.length} onClick={exportProfile} type="button"><span>{exportLabel(t)}</span></button>
        <button disabled={disabled || !profileText.trim()} onClick={importProfile} type="button"><span>{importLabel(t)}</span></button>
      </div>
      <div className="search-form">
        <input value={profileName} onChange={(event) => setProfileName(event.target.value)} placeholder={profileNameLabel(t)} />
        <input value={profileDomain} onChange={(event) => setProfileDomain(event.target.value)} placeholder={profileDomainLabel(t)} />
        <button disabled={disabled || !checks.length || !profileName.trim()} onClick={saveReusableProfile} type="button">
          <span>{savedLabel(t)}</span>
        </button>
      </div>
      <div className="search-form">
        <select value={selectedProfile} onChange={(event) => setSelectedProfile(event.target.value)}>
          {profiles.map((profile) => (
            <option value={String(profile.id)} key={String(profile.id)}>{profileTitle(profile)}</option>
          ))}
        </select>
        <button disabled={disabled || !selectedProfile} onClick={applyReusableProfile} type="button"><span>{applyLabel(t)}</span></button>
      </div>
      <textarea
        value={profileText}
        onChange={(event) => setProfileText(event.target.value)}
        placeholder={profileLabel(t)}
        rows={4}
      />
      {status && <code>{status}</code>}
      <GoldenGatePanel datasetId={datasetId} refreshKey={`${checks.length}:${runs.length}:${status}`} t={t} />
      {checks.slice(0, 6).map((check) => <GoldenRow check={check} onDelete={remove} t={t} key={String(check.id)} />)}
      {runs.length > 0 && (
        <div className="ai-summary-list">
          <strong>{historyLabel(t)}</strong>
          {runs.slice(0, 5).map((run) => <RunRow run={run} key={String(run.id)} />)}
        </div>
      )}
    </div>
  );
}

function GoldenRow({ check, onDelete, t }: { check: Record<string, unknown>; onDelete: (id: string) => void; t: Props["t"] }) {
  const result = objectValue(check.last_result);
  const missing = Array.isArray(result.missing_terms) ? result.missing_terms.map(String).join(", ") : "";
  return (
    <span className="history-row">
      <b>{String(result.status ?? "pending")} · {String(result.score ?? 0)}%</b>
      {String(check.question ?? "")}
      {missing ? ` · ${t("missing")}: ${missing}` : ""}
      <button onClick={() => onDelete(String(check.id))} type="button">{t("delete")}</button>
    </span>
  );
}

function downloadProfile(profile: Record<string, unknown>) {
  const blob = new Blob([JSON.stringify(profile, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = "datarules-golden-checks.json";
  link.click();
  URL.revokeObjectURL(url);
}

function RunRow({ run }: { run: Record<string, unknown> }) {
  const result = objectValue(run.result);
  const delta = objectValue(run.delta ?? result.delta);
  const snapshot = objectValue(run.snapshot ?? result.snapshot);
  return (
    <span className="history-row">
      <b>{String(run.status)} · {String(run.score)}%</b>
      {String(run.passed ?? 0)} / {String(run.total ?? 0)} {deltaText(delta)}
      <small>{[snapshotText(snapshot), String(run.created_at ?? "")].filter(Boolean).join(" · ")}</small>
    </span>
  );
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function recordArray(value: unknown): Array<Record<string, unknown>> {
  return Array.isArray(value) ? value.filter((item) => typeof item === "object") as Array<Record<string, unknown>> : [];
}

function lang(t: Props["t"]) {
  return t("language");
}

function goldenLabel(t: Props["t"]) {
  if (lang(t) === "Язык") return "Контрольные вопросы качества";
  if (lang(t) === "Тіл") return "Сапа бақылау сұрақтары";
  return "Golden answer checks";
}

function questionLabel(t: Props["t"]) {
  if (lang(t) === "Язык") return "Контрольный вопрос";
  if (lang(t) === "Тіл") return "Бақылау сұрағы";
  return "Expected question";
}

function termsLabel(t: Props["t"]) {
  if (lang(t) === "Язык") return "Ожидаемые слова через запятую";
  if (lang(t) === "Тіл") return "Күтілетін сөздер, үтірмен";
  return "Expected terms, comma-separated";
}

function exportLabel(t: Props["t"]) {
  if (lang(t) === "Язык") return "Экспорт JSON";
  if (lang(t) === "Тіл") return "JSON экспорт";
  return "Export JSON";
}

function importLabel(t: Props["t"]) {
  if (lang(t) === "Язык") return "Импорт JSON";
  if (lang(t) === "Тіл") return "JSON импорт";
  return "Import JSON";
}

function profileLabel(t: Props["t"]) {
  if (lang(t) === "Язык") return "JSON профиль контрольных вопросов";
  if (lang(t) === "Тіл") return "Бақылау сұрақтарының JSON профилі";
  return "Golden checks JSON profile";
}

function importedLabel(t: Props["t"]) {
  if (lang(t) === "Язык") return "Импортировано";
  if (lang(t) === "Тіл") return "Импортталды";
  return "Imported";
}

function savedLabel(t: Props["t"]) {
  if (lang(t) === "Язык") return "Сохранить профиль";
  if (lang(t) === "Тіл") return "Профиль сақтау";
  return "Save profile";
}

function applyLabel(t: Props["t"]) {
  if (lang(t) === "Язык") return "Применить профиль";
  if (lang(t) === "Тіл") return "Профиль қолдану";
  return "Apply profile";
}

function profileNameLabel(t: Props["t"]) {
  if (lang(t) === "Язык") return "Название профиля";
  if (lang(t) === "Тіл") return "Профиль атауы";
  return "Profile name";
}

function profileDomainLabel(t: Props["t"]) {
  if (lang(t) === "Язык") return "Тип датасета";
  if (lang(t) === "Тіл") return "Датасет түрі";
  return "Dataset type";
}

function profileTitle(profile: Record<string, unknown>) {
  return `${String(profile.domain ?? "general")} · ${String(profile.name ?? "")} v${String(profile.version ?? 1)}`;
}

function deltaText(delta: Record<string, unknown>) {
  if (!Object.keys(delta).length || delta.score_delta === null || delta.score_delta === undefined) return "";
  const regressions = Array.isArray(delta.regressions) ? delta.regressions.length : 0;
  const improvements = Array.isArray(delta.improvements) ? delta.improvements.length : 0;
  const score = Number(delta.score_delta);
  return `· Δ ${score > 0 ? "+" : ""}${score} · ↓${regressions} ↑${improvements}`;
}

function snapshotText(snapshot: Record<string, unknown>) {
  if (!Object.keys(snapshot).length) return "";
  const ready = snapshot.ready_agent_tables === undefined ? "" : `agent ${String(snapshot.ready_agent_tables)}`;
  return [snapshot.answer_prompt_version, snapshot.embedding_model_id, ready].filter(Boolean).map(String).join(" · ");
}

function historyLabel(t: Props["t"]) {
  if (lang(t) === "Язык") return "История прогонов";
  if (lang(t) === "Тіл") return "Іске қосу тарихы";
  return "Run history";
}
