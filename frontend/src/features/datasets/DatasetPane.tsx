import { Database, Plus, RefreshCw } from "lucide-react";
import { FormEvent, useState } from "react";
import type { Dataset } from "@shared/types";

type Props = {
  datasets: Dataset[];
  selected?: Dataset;
  onCreate: (name: string, description: string) => Promise<void>;
  onRefresh: () => Promise<void>;
  onSelect: (dataset: Dataset) => void;
  t: (key: string) => string;
};

export function DatasetPane({ datasets, selected, onCreate, onRefresh, onSelect, t }: Props) {
  const [name, setName] = useState("Investment projects");
  const [description, setDescription] = useState("Projects, companies, amounts, dates, status.");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await onCreate(name, description);
      setName("");
      setDescription("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside className="sidebar">
      <div className="pane-title">
        <Database size={18} />
        <span>{t("datasets")}</span>
        <button className="icon-button" onClick={onRefresh} title={t("refresh")}>
          <RefreshCw size={16} />
        </button>
      </div>

      <form className="dataset-form" onSubmit={submit}>
        <input
          value={name}
          onChange={(event) => setName(event.target.value)}
          placeholder={t("datasetName")}
          required
        />
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          placeholder={t("datasetDescription")}
          rows={3}
        />
        <button disabled={busy || !name.trim()} type="submit">
          <Plus size={16} />
          <span>{t("createDataset")}</span>
        </button>
      </form>

      <div className="dataset-list">
        {datasets.map((dataset) => (
          <button
            className={dataset.id === selected?.id ? "dataset-row active" : "dataset-row"}
            key={dataset.id}
            onClick={() => onSelect(dataset)}
          >
            <span>{dataset.name}</span>
            <small>{dataset.status}</small>
          </button>
        ))}
      </div>
    </aside>
  );
}
