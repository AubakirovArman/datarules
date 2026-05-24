import { useState } from "react";
import { AppHeader } from "@app/AppHeader";
import { useAppController } from "@app/useAppController";
import { DatasetsPage } from "@pages/DatasetsPage";
import { FlowPage } from "@pages/FlowPage";
import { SettingsPage } from "@pages/SettingsPage";
import { api } from "@shared/api";
import { extraCopy } from "@shared/i18n/simple";
import { copy, type Language } from "@shared/i18n";

import type { AppPage } from "@app/AppHeader";

export function App() {
  const [page, setPage] = useState<AppPage>("flow");
  const [language, setLanguage] = useState<Language>(() => {
    return (localStorage.getItem("datarules-language") as Language) || "ru";
  });

  const t = (key: string) => copy[language][key] ?? extraCopy[language][key] ?? copy.en[key] ?? extraCopy.en[key] ?? key;

  const controller = useAppController({
    t,
    language,
    onNavigateFlow: () => setPage("flow"),
  });

  return (
    <main className="product-shell">
      <AppHeader
        page={page}
        datasets={controller.datasets}
        selected={controller.selected}
        health={controller.health}
        language={language}
        onPage={setPage}
        onSelect={controller.selectDataset}
        onLanguage={(next) => {
          localStorage.setItem("datarules-language", next);
          setLanguage(next);
        }}
        t={t}
      />
      <section className="workspace">
        {controller.error && <div className="error-banner">{controller.error}</div>}
        {page === "datasets" && (
          <DatasetsPage
            datasets={controller.datasets}
            selected={controller.selected}
            onCreate={controller.createDataset}
            onRefresh={controller.loadDatasets}
            onSelect={controller.selectDataset}
            t={t}
          />
        )}
        {page === "settings" && (
          <SettingsPage
            connections={controller.connections}
            tables={controller.tables}
            onCreate={(name, description, url, schema) =>
              Promise.resolve()
                .then(() => api.createConnection(name, description, url, schema))
                .then(() => controller.loadDbSettings())
            }
            onIntrospect={(connectionId) =>
              api
                .introspectConnection(connectionId)
                .then(() => controller.loadDbSettings())
            }
            onWritePolicy={(connectionId, enabled, schemas, confirmed) =>
              api
                .updateWritePolicy(connectionId, enabled, schemas, Boolean(confirmed))
                .then(() => controller.loadDbSettings())
            }
            t={t}
          />
        )}
        {page === "flow" && (
          <FlowPage
            selected={Boolean(controller.selected)}
            disabled={controller.selectedDisabled}
            files={controller.files}
            job={controller.job}
            events={controller.events}
            summaries={controller.summaries}
            reviews={controller.reviews}
            proposals={controller.proposals}
            loadPlans={controller.loadPlans}
            connections={controller.connections}
            tables={controller.tables}
            datasetId={controller.selected?.id}
            onUpload={controller.onUpload}
            onDelete={controller.onDelete}
            onRefreshFiles={controller.onRefreshFiles}
            onStart={controller.onStart}
            onRefreshSummaries={controller.onRefreshSummaries}
            onRefreshReviews={controller.onRefreshReviews}
            onConfirmReview={controller.onConfirmReview}
            onRefreshProposals={controller.onRefreshProposals}
            onApproveSchema={controller.onApproveSchema}
            onSchemaChat={controller.onSchemaChat}
            onCreateLoadPlan={controller.onCreateLoadPlan}
            onUpdateLoadPlanRows={controller.onUpdateLoadPlanRows}
            onConfirmLoadPlan={controller.onConfirmLoadPlan}
            onSearch={controller.onSearch}
            onAsk={controller.onAsk}
            t={t}
          />
        )}
      </section>
    </main>
  );
}
