import type { Dataset } from "@shared/types";
import { DatasetPane } from "@features/datasets/DatasetPane";

type Props = {
  datasets: Dataset[];
  selected?: Dataset;
  onCreate: (name: string, description: string) => Promise<void>;
  onRefresh: () => Promise<void>;
  onSelect: (dataset: Dataset) => void;
  t: (key: string) => string;
};

export function DatasetsPage({ datasets, selected, onCreate, onRefresh, onSelect, t }: Props) {
  return (
    <section className="dataset-page">
      <DatasetPane
        datasets={datasets}
        selected={selected}
        onCreate={onCreate}
        onRefresh={onRefresh}
        onSelect={onSelect}
        t={t}
      />
    </section>
  );
}
