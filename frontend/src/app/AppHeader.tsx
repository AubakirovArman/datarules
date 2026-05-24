import { Database, Languages, Settings2, Workflow } from "lucide-react";
import { languages, type Language } from "@shared/i18n";
import type { Dataset } from "@shared/types";

export type AppPage = "flow" | "datasets" | "settings";

type Props = {
  page: AppPage;
  datasets: Dataset[];
  selected?: Dataset;
  health: Record<string, unknown>;
  language: Language;
  onPage: (page: AppPage) => void;
  onSelect: (dataset: Dataset) => void;
  onLanguage: (language: Language) => void;
  t: (key: string) => string;
};

export function AppHeader(props: Props) {
  return (
    <header className="topbar product-topbar">
      <div className="brand-block">
        <span className="workflow-title">DataRules</span>
        <h1>{props.selected?.name ?? "DataRules"}</h1>
        <p>{props.selected?.description ?? props.t("createAndUpload")}</p>
      </div>
      <nav className="app-nav" aria-label={props.t("workflow")}>
        <button className={props.page === "flow" ? "active" : ""} onClick={() => props.onPage("flow")} type="button">
          <Workflow size={16} />
          <span>{props.t("workflow")}</span>
        </button>
        <button className={props.page === "datasets" ? "active" : ""} onClick={() => props.onPage("datasets")} type="button">
          <Database size={16} />
          <span>{props.t("datasets")}</span>
        </button>
        <button className={props.page === "settings" ? "active" : ""} onClick={() => props.onPage("settings")} type="button">
          <Settings2 size={16} />
          <span>{props.t("settings")}</span>
        </button>
      </nav>
      <div className="runtime compact-runtime">
        <label>
          <span>{props.t("datasets")}</span>
          <select value={props.selected?.id ?? ""} onChange={(event) => chooseDataset(event.target.value, props)}>
            <option value="">{props.t("autoDatasetName")}</option>
            {props.datasets.map((dataset) => <option value={dataset.id} key={dataset.id}>{dataset.name}</option>)}
          </select>
        </label>
        <span>Gemma</span>
        <strong>{String(props.health.gemma_model_id ?? props.t("notChecked"))}</strong>
        <small>GPU {String(props.health.gemma_gpu_id ?? 2)}</small>
        <label>
          <span><Languages size={13} /> {props.t("language")}</span>
          <select className="lang-select" value={props.language} onChange={(event) => props.onLanguage(event.target.value as Language)}>
            {languages.map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
        </label>
      </div>
    </header>
  );
}

function chooseDataset(id: string, props: Props) {
  const dataset = props.datasets.find((item) => item.id === id);
  if (dataset) props.onSelect(dataset);
}
