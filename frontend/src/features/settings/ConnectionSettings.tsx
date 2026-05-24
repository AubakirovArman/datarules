import { Database, RefreshCw, Settings2 } from "lucide-react";
import { FormEvent, useState } from "react";
import { api } from "@shared/api";
import type { DbConnection, TableCatalog } from "@shared/types";
import { AuditTrail } from "./AuditTrail";
import { RuntimeDiagnostics } from "./RuntimeDiagnostics";

type Props = {
  connections: DbConnection[];
  tables: TableCatalog[];
  onCreate: (name: string, description: string, url: string, schema: string) => Promise<void>;
  onIntrospect: (connectionId: string) => Promise<void>;
  onWritePolicy: (connectionId: string, enabled: boolean, schemas: string[], confirmed?: boolean) => Promise<void>;
  t: (key: string) => string;
};

export function ConnectionSettings({ connections, tables, onCreate, onIntrospect, onWritePolicy, t }: Props) {
  const [open, setOpen] = useState(false);
  const [name, setName] = useState("External PostgreSQL");
  const [description, setDescription] = useState("");
  const [url, setUrl] = useState("postgresql+psycopg://user:password@127.0.0.1:55433/dbname");
  const [schema, setSchema] = useState("public");
  const [busy, setBusy] = useState(false);
  const [testState, setTestState] = useState<Record<string, string>>({});

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    try {
      await onCreate(name, description, url, schema);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel settings-panel">
      <div className="panel-head">
        <h2>{t("dbSettings")}</h2>
        <button className="icon-button" onClick={() => setOpen((value) => !value)} title={t("settings")}>
          <Settings2 size={16} />
        </button>
      </div>
      <div className="connection-list">
        {connections.map((connection) => (
          <article className="connection-card" key={connection.id}>
            <Database size={16} />
            <div>
              <strong>{connection.name}</strong>
              <small>{connection.description || connection.default_schema}</small>
              <code>{connectionDisplay(connection)}</code>
            </div>
            <span>{capabilityText(connection.capabilities_json)}</span>
            <span>{testState[connection.id] || connectionStatus(connection, t)}</span>
            <span>{writePolicyText(connection, t)}</span>
            <button onClick={() => testConnection(connection.id, setTestState, t)} type="button">
              <RefreshCw size={15} />
              <span>{t("connectionStatus")}</span>
            </button>
            <button onClick={() => onIntrospect(connection.id)}>
              <RefreshCw size={15} />
              <span>{t("introspect")}</span>
            </button>
            {!connection.is_internal && (
              <button onClick={() => toggleWrites(connection, onWritePolicy, t)}>
                <span>{writeEnabled(connection) ? t("disableWrites") : t("enableWrites")}</span>
              </button>
            )}
          </article>
        ))}
      </div>
      {open && (
        <form className="connection-form" onSubmit={submit}>
          <input value={name} onChange={(event) => setName(event.target.value)} placeholder={t("connectionName")} />
          <input
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder={t("connectionDescription")}
          />
          <input value={url} onChange={(event) => setUrl(event.target.value)} placeholder={t("connectionUrl")} />
          <input value={schema} onChange={(event) => setSchema(event.target.value)} placeholder={t("schemaName")} />
          <button disabled={busy || !name.trim() || !url.trim()}>
            <Database size={16} />
            <span>{t("saveConnection")}</span>
          </button>
        </form>
      )}
      <div className="table-catalog-strip">
        <strong>{t("knownTables")}</strong>
        <span>{tables.length}</span>
      </div>
      <div className="connection-list">
        {tables.slice(0, 8).map((table) => (
          <article className="connection-card" key={table.id}>
            <Database size={16} />
            <div>
              <strong>{table.schema_name}.{table.table_name}</strong>
              <small>{table.description || catalogSearchText(table.agent_profile_json)}</small>
              <code>{columnPreview(table.columns_json) || t("readinessStatus_pending")}</code>
            </div>
            <span>{table.columns_json.length} {t("fields")}</span>
            <span>{table.can_create_rows ? t("writesEnabled") : t("writesReadOnly")}</span>
          </article>
        ))}
      </div>
      <RuntimeDiagnostics t={t} />
      <AuditTrail t={t} />
    </section>
  );
}

function capabilityText(value: Record<string, unknown>) {
  const flags = ["vector", "bm25", "trigram"].filter((key) => value[key]);
  return flags.length ? flags.join(" + ") : "metadata";
}

function connectionDisplay(connection: DbConnection) {
  const meta = objectValue(connection.capabilities_json.connection);
  return String(meta.display_url ?? `${connection.default_schema}`);
}

function connectionStatus(connection: DbConnection, t: Props["t"]) {
  const meta = objectValue(connection.capabilities_json.connection);
  const status = String(meta.last_status ?? "unknown");
  const zone = String(meta.network_zone ?? "unknown");
  return `${t("connectionStatus")}: ${status} · ${zone}`;
}

function objectValue(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

async function testConnection(id: string, setState: (value: Record<string, string>) => void, t: Props["t"]) {
  setState({ [id]: `${t("connectionStatus")}: ${t("readinessStatus_pending")}` });
  try {
    await api.testConnection(id);
    setState({ [id]: `${t("connectionStatus")}: ${t("ready")}` });
  } catch (error) {
    setState({ [id]: `${t("connectionStatus")}: ${error instanceof Error ? error.message : "failed"}` });
  }
}

function toggleWrites(connection: DbConnection, onWritePolicy: Props["onWritePolicy"], t: Props["t"]) {
  const enabled = !writeEnabled(connection);
  const confirmed = !enabled || window.confirm(t("confirmExternalWrites"));
  if (!confirmed) return;
  onWritePolicy(connection.id, enabled, [connection.default_schema], enabled);
}

function writeEnabled(connection: DbConnection) {
  const policy = connection.capabilities_json.write_policy;
  return Boolean(policy && typeof policy === "object" && (policy as Record<string, unknown>).enabled);
}

function writePolicyText(connection: DbConnection, t: Props["t"]) {
  if (connection.is_internal) return t("writesInternal");
  const policy = connection.capabilities_json.write_policy as Record<string, unknown> | undefined;
  const schemas = Array.isArray(policy?.schemas) ? policy?.schemas.join(", ") : connection.default_schema;
  return writeEnabled(connection) ? `${t("writesEnabled")}: ${schemas}` : t("writesReadOnly");
}

function columnPreview(columns: Array<Record<string, unknown>>) {
  return columns.slice(0, 4).map((column) => `${String(column.name)}:${String(column.type)}`).join(" · ");
}

function catalogSearchText(profile: Record<string, unknown>) {
  const search = objectValue(profile.search);
  return ["semantic", "keyword", "bm25"].filter((key) => search[key]).join(" + ") || "agent catalog";
}
