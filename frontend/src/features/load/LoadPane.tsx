import { DatabaseZap, PlayCircle } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { api } from "@shared/api";
import type { DbConnection, DocumentFile, DocumentReview, LoadPlan, TableCatalog } from "@shared/types";
import { AgentReadinessReport } from "./AgentReadinessReport";
import { LoadedRowsBrowser } from "./LoadedRowsBrowser";
import { LoadDocumentPicker } from "./LoadDocumentPicker";
import { LoadIssues } from "./LoadIssues";
import { LoadPlanActions } from "./LoadPlanActions";
import { LoadPlanTimeline } from "./LoadPlanTimeline";
import { LoadPreflight } from "./LoadPreflight";
import { LoadQuarantinePanel } from "./LoadQuarantinePanel";
import { LoadReport } from "./LoadReport";
import { PreviewEditor } from "./PreviewEditor";

type Props = {
  connections: DbConnection[];
  files: DocumentFile[];
  tables: TableCatalog[];
  reviews: DocumentReview[];
  plans: LoadPlan[];
  datasetId?: string;
  onCreatePlan: (
    connectionId: string | undefined,
    schema: string,
    mode: string,
    table: string,
    schemaJson?: Record<string, unknown>,
    documentIds?: string[],
    schemaVersionId?: string,
  ) => Promise<LoadPlan | undefined>;
  onUpdateRows: (planId: string, rows: LoadPlan["preview_rows"]) => Promise<void>;
  onConfirm: (planId: string) => Promise<void>;
  t: (key: string) => string;
};

type Destination = {
  connectionId?: string;
  schema: string;
  table: string;
  key: string;
  label: string;
};

export function LoadPane({ connections, files, tables, reviews, plans, datasetId, onCreatePlan, onUpdateRows, onConfirm, t }: Props) {
  const destinations = useMemo(() => tableOptions(tables, reviews), [tables, reviews]);
  const defaultConnection = connections.find((item) => item.is_internal) ?? connections[0];
  const first = destinations[0];
  const [mode, setMode] = useState("existing");
  const [connectionId, setConnectionId] = useState(defaultConnection?.id ?? first?.connectionId ?? "");
  const [schema, setSchema] = useState(defaultConnection?.default_schema ?? first?.schema ?? "public");
  const [table, setTable] = useState(first?.table ?? "investment_projects");
  const [destinationKey, setDestinationKey] = useState(first?.key ?? "");
  const [documentIds, setDocumentIds] = useState<string[]>([]);
  const [schemaVersions, setSchemaVersions] = useState<Array<Record<string, unknown>>>([]);
  const [schemaVersionId, setSchemaVersionId] = useState("");
  const [localPlan, setLocalPlan] = useState<LoadPlan>();
  const [busy, setBusy] = useState(false);
  const plan = localPlan ?? plans[0];
  const preflightBlocked = reviews.some((review) => review.status !== "confirmed");

  useEffect(() => {
    if (!connectionId && defaultConnection) {
      setConnectionId(defaultConnection.id);
      setSchema(defaultConnection.default_schema);
    }
  }, [connectionId, defaultConnection]);

  useEffect(() => {
    if (mode === "existing" && first && !destinations.some((item) => item.key === destinationKey)) {
      applyDestination(first);
    }
  }, [mode, destinations, first, destinationKey]);

  useEffect(() => {
    setDocumentIds(files.map((file) => file.id));
  }, [files]);

  useEffect(() => {
    if (!datasetId) return;
    void api.schemaVersions(datasetId).then((rows) => {
      setSchemaVersions(rows);
      const active = rows.find((item) => item.status === "active") ?? rows[0];
      if (active && !schemaVersionId) setSchemaVersionId(String(active.id ?? ""));
    });
  }, [datasetId]);

  useEffect(() => {
    setLocalPlan(undefined);
  }, [plans[0]?.id, plans[0]?.updated_at]);

  async function build() {
    setBusy(true);
    try {
      await onCreatePlan(connectionId || undefined, schema || "public", mode, table, undefined, documentIds, schemaVersionId || undefined);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel load-panel">
      <div className="panel-head">
        <h2>{t("previewLoad")}</h2>
        <DatabaseZap size={18} />
      </div>
      <p className="panel-hint">{t("loadHint")}</p>
      <LoadPreflight
        documentIds={documentIds}
        reviews={reviews}
        schemaVersionId={schemaVersionId}
        schemaVersions={schemaVersions}
        table={table}
        t={t}
      />
      <div className="load-controls">
        <div className="segmented">
          <button className={mode === "existing" ? "active" : ""} onClick={() => setMode("existing")}>
            {t("existingTable")}
          </button>
          <button className={mode === "new" ? "active" : ""} onClick={() => setMode("new")}>
            {t("newTable")}
          </button>
          <button className={mode === "analysis_only" ? "active" : ""} onClick={() => useAnalysisOnly()}>
            {t("analysisOnly")}
          </button>
        </div>
        <select value={connectionId} onChange={(event) => setConnectionId(event.target.value)}>
          {connections.map((connection) => (
            <option value={connection.id} key={connection.id}>{connection.name}</option>
          ))}
        </select>
        <input value={schema} onChange={(event) => setSchema(event.target.value)} placeholder={t("schemaName")} />
        {schemaVersions.length > 0 && (
          <select value={schemaVersionId} onChange={(event) => chooseSchemaVersion(event.target.value)}>
            <option value="">{t("schemaVersionNone")}</option>
            {schemaVersions.map((version) => (
              <option value={String(version.id)} key={String(version.id)}>
                {schemaVersionLabel(version)}
              </option>
            ))}
          </select>
        )}
        {mode === "existing" ? (
          <select value={destinationKey} onChange={(event) => {
            const option = destinations.find((item) => item.key === event.target.value);
            if (option) applyDestination(option);
          }}>
            {destinations.map((option) => (
              <option value={option.key} key={option.key}>
                {option.label}
              </option>
            ))}
          </select>
        ) : mode === "new" ? (
          <input value={table} onChange={(event) => setTable(event.target.value)} placeholder={t("targetName")} />
        ) : (
          <input value={table} disabled title={t("analysisOnly")} />
        )}
        <button disabled={busy || preflightBlocked || !table.trim() || documentIds.length === 0} onClick={build}>
          <PlayCircle size={16} />
          <span>{t("buildPreview")}</span>
        </button>
      </div>
      <LoadDocumentPicker files={files} selectedIds={documentIds} onChange={setDocumentIds} t={t} />
      {plan && <PlanPreview plan={plan} preflightBlocked={preflightBlocked} onPlanUpdated={setLocalPlan} onUpdateRows={onUpdateRows} onConfirm={onConfirm} t={t} />}
    </section>
  );

  function applyDestination(option: Destination) {
    if (option.table === "analysis_only") setMode("analysis_only");
    setDestinationKey(option.key);
    setConnectionId(option.connectionId ?? "");
    setSchema(option.schema);
    setTable(option.table);
  }

  function useAnalysisOnly() {
    setMode("analysis_only");
    setTable("analysis_only");
  }

  function chooseSchemaVersion(id: string) {
    setSchemaVersionId(id);
    const version = schemaVersions.find((item) => item.id === id);
    const name = version ? firstTableName(version) : "";
    if (name) setTable(name);
  }
}

function schemaVersionLabel(version: Record<string, unknown>) {
  const table = firstTableName(version);
  return `v${String(version.version)} · ${String(version.status)}${table ? ` · ${table}` : ""}`;
}

function firstTableName(version: Record<string, unknown>) {
  const schema = version.schema_json as Record<string, unknown> | undefined;
  const tables = Array.isArray(schema?.tables) ? schema.tables : [];
  const table = tables[0] as Record<string, unknown> | undefined;
  return String(table?.name ?? table?.table_name ?? "");
}

function PlanPreview({
  plan,
  preflightBlocked,
  onUpdateRows,
  onConfirm,
  onPlanUpdated,
  t,
}: {
  plan: LoadPlan;
  preflightBlocked: boolean;
  onUpdateRows: Props["onUpdateRows"];
  onConfirm: Props["onConfirm"];
  onPlanUpdated: (plan: LoadPlan) => void;
  t: Props["t"];
}) {
  const [dirty, setDirty] = useState(false);
  return (
    <div className="load-preview">
      <div className="load-status">
        <h3>{plan.schema_name}.{plan.target_table}</h3>
        <span className={`status ${plan.status}`}>{t(plan.status)}</span>
        <small>{plan.preview_rows.length} {t("rows")}</small>
      </div>
      <AgentReadinessReport value={plan.agent_preparation_json} t={t} />
      <LoadReport planId={plan.id} refreshKey={plan.updated_at} t={t} />
      <LoadedRowsBrowser planId={plan.id} enabled={plan.status === "loaded" && plan.target_mode !== "analysis_only"} refreshKey={plan.updated_at} t={t} />
      <LoadIssues issues={plan.validation_issues} t={t} />
      <LoadQuarantinePanel planId={plan.id} refreshKey={plan.updated_at} t={t} />
      <LoadPlanTimeline events={plan.events} />
      <PreviewEditor plan={plan} onSave={(rows) => onUpdateRows(plan.id, rows)} onDirtyChange={setDirty} t={t} />
      {dirty && <small className="load-save-warning">{t("savePreviewBeforeLoad")}</small>}
      <LoadPlanActions plan={plan} preflightBlocked={preflightBlocked} dirty={dirty} onConfirm={onConfirm} onPlanUpdated={onPlanUpdated} t={t} />
    </div>
  );
}

function tableOptions(tables: TableCatalog[], reviews: DocumentReview[]) {
  const catalog = tables.map((table) => ({
    connectionId: table.connection_id,
    schema: table.schema_name,
    table: table.table_name,
    key: destinationKey(table.connection_id, table.schema_name, table.table_name),
    label: `${table.schema_name}.${table.table_name} · ${table.description || "catalog"}`,
  }));
  const routed = reviews.flatMap((review) =>
    review.table_options.map((option) => ({
      connectionId: option.connection_id,
      schema: option.schema_name ?? "public",
      table: option.value,
      key: destinationKey(option.connection_id, option.schema_name ?? "public", option.value),
      label: option.label,
    })),
  );
  return uniqueDestinations([...catalog, ...routed]);
}

function uniqueDestinations(items: Destination[]) {
  const seen = new Set<string>();
  return items.filter((item) => {
    const key = `${item.connectionId}-${item.schema}-${item.table}`;
    if (seen.has(key)) return false;
    seen.add(key);
    return true;
  });
}

function destinationKey(connectionId: string | undefined, schema: string, table: string) {
  return `${connectionId ?? "internal"}:${schema}:${table}`;
}
