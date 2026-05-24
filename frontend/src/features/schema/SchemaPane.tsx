import { Check, RefreshCw } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@shared/api";
import type { SchemaProposal } from "@shared/types";

type Props = {
  datasetId?: string;
  proposals: SchemaProposal[];
  onRefresh: () => Promise<void>;
  onApprove: (id: string) => Promise<void>;
  t: (key: string) => string;
};

export function SchemaPane({ datasetId, proposals, onRefresh, onApprove, t }: Props) {
  const [versions, setVersions] = useState<Array<Record<string, unknown>>>([]);
  const [selectedId, setSelectedId] = useState("");
  const proposal = proposals.find((item) => item.id === selectedId) ?? proposals[0];
  const tables = Array.isArray(proposal?.proposal_json.tables)
    ? (proposal?.proposal_json.tables as Array<Record<string, unknown>>)
    : [];

  async function refreshVersions() {
    if (!datasetId) return;
    setVersions(await api.schemaVersions(datasetId));
  }

  useEffect(() => {
    void refreshVersions();
  }, [datasetId, proposals]);

  useEffect(() => {
    if (!proposals.length) {
      setSelectedId("");
      return;
    }
    if (!proposals.some((item) => item.id === selectedId)) setSelectedId(proposals[0].id);
  }, [proposals, selectedId]);

  async function approve() {
    if (!proposal) return;
    await onApprove(proposal.id);
    await refreshVersions();
  }

  return (
    <section className="panel">
      <div className="panel-head">
        <h2>{t("schema")}</h2>
        <div className="toolbar">
          <button className="icon-button" onClick={onRefresh} title={t("refresh")}>
            <RefreshCw size={16} />
          </button>
          <button disabled={!proposal || proposal.status === "approved"} onClick={approve}>
            <Check size={16} />
            <span>{t("approve")}</span>
          </button>
        </div>
      </div>
      {!proposal && <div className="empty">{t("noSchema")}</div>}
      {proposal && (
        <>
          <ProposalChooser proposals={proposals} selectedId={proposal.id} onSelect={setSelectedId} t={t} />
          <div className="schema-summary">{String(proposal.proposal_json.dataset_summary ?? "")}</div>
          <div className="schema-grid">
            {tables.map((table) => (
              <div className="schema-table" key={String(table.name)}>
                <strong>{String(table.name)}</strong>
                <small>{String(table.purpose ?? "")}</small>
                <ul>
                  {Array.isArray(table.columns) &&
                    table.columns.slice(0, 8).map((column) => {
                      const item = column as Record<string, unknown>;
                      return (
                        <li key={String(item.name)}>
                          <span>{String(item.name)}</span>
                          <small>{String(item.type)}</small>
                        </li>
                      );
                    })}
                </ul>
              </div>
            ))}
          </div>
          <SchemaVersions versions={versions} t={t} />
        </>
      )}
      {!proposal && <SchemaVersions versions={versions} t={t} />}
    </section>
  );
}

function ProposalChooser({
  proposals,
  selectedId,
  onSelect,
  t,
}: {
  proposals: SchemaProposal[];
  selectedId: string;
  onSelect: (id: string) => void;
  t: Props["t"];
}) {
  if (proposals.length < 2) return null;
  return (
    <div className="proposal-chooser">
      <strong>{t("schemaProposalOptions")}</strong>
      <div>
        {proposals.slice(0, 8).map((proposal, index) => (
          <button
            className={proposal.id === selectedId ? "active" : ""}
            onClick={() => onSelect(proposal.id)}
            type="button"
            key={proposal.id}
          >
            <span>{proposalTitle(proposal, index, t)}</span>
            <small>{t(proposal.status)} · {proposalTableCount(proposal)} {t("tables")}</small>
          </button>
        ))}
      </div>
    </div>
  );
}

function proposalTitle(proposal: SchemaProposal, index: number, t: Props["t"]) {
  const schema = proposal.proposal_json;
  const title = schema.title ?? schema.name ?? schema.dataset_name;
  return title ? String(title) : `${t("proposal")} ${index + 1}`;
}

function proposalTableCount(proposal: SchemaProposal) {
  return Array.isArray(proposal.proposal_json.tables) ? proposal.proposal_json.tables.length : 0;
}

function SchemaVersions({ versions, t }: { versions: Array<Record<string, unknown>>; t: Props["t"] }) {
  if (versions.length === 0) return null;
  return (
    <div className="ai-summary-list">
      <strong>{t("schemaVersions")}</strong>
      {versions.slice(0, 5).map((version) => (
        <span key={String(version.id)}>
          v{String(version.version)} · {t(String(version.status))} · {versionSummary(version)}
        </span>
      ))}
    </div>
  );
}

function versionSummary(version: Record<string, unknown>) {
  const schema = version.schema_json as Record<string, unknown> | undefined;
  const tables = Array.isArray(schema?.tables) ? schema?.tables : [];
  if (tables.length > 0) {
    return tables.slice(0, 3).map((item) => {
      const table = item as Record<string, unknown>;
      return String(table.name ?? table.table_name ?? item);
    }).join(", ");
  }
  return String(version.summary ?? "");
}
