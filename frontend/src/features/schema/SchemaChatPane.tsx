import { MessageSquare, Send } from "lucide-react";
import { FormEvent, useState } from "react";
import type { SchemaChatResponse } from "@shared/types";

type Props = {
  disabled: boolean;
  onAsk: (message: string) => Promise<SchemaChatResponse>;
  onUseProposal?: (proposal: Record<string, unknown>) => Promise<unknown>;
  t: (key: string) => string;
};

export function SchemaChatPane({ disabled, onAsk, onUseProposal, t }: Props) {
  const [input, setInput] = useState(t("schemaChatDefault"));
  const [messages, setMessages] = useState<Array<{ role: string; text: string }>>([]);
  const [proposal, setProposal] = useState<Record<string, unknown> | undefined>();
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    if (!input.trim()) return;
    const userText = input.trim();
    setMessages((items) => [...items, { role: "user", text: userText }]);
    setInput("");
    setBusy(true);
    try {
      const response = await onAsk(userText);
      setMessages((items) => [...items, { role: "assistant", text: response.assistant_message }]);
      setProposal(response.proposal_json);
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="panel chat-panel">
      <div className="panel-head">
        <h2>{t("schemaChat")}</h2>
        <MessageSquare size={18} />
      </div>
      <div className="chat-log">
        {messages.map((message, index) => (
          <div className={`chat-bubble ${message.role}`} key={`${message.role}-${index}`}>
            {message.text}
          </div>
        ))}
      </div>
      {proposal && (
        <div className="proposal-box">
          <strong>{t("proposal")}: {String(proposal.table_name ?? "table")}</strong>
          <small>{t("chatContext")}: {formatContext(proposal.context_usage)}</small>
          <code>{JSON.stringify(proposal.columns ?? proposal, null, 2)}</code>
          {Array.isArray(proposal.identifier_warnings) && proposal.identifier_warnings.length > 0 && (
            <small>{t("schemaWarnings")}: {proposal.identifier_warnings.length}</small>
          )}
          <small>{t("nextStep")}: {String(proposal.next_confirmation_step ?? "")}</small>
          {onUseProposal && (
            <button disabled={busy} onClick={() => onUseProposal(proposal)}>
              <span>{t("buildPreview")}</span>
            </button>
          )}
        </div>
      )}
      <form className="chat-form" onSubmit={submit}>
        <input
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={t("askSchema")}
          disabled={disabled || busy}
        />
        <button disabled={disabled || busy || !input.trim()} type="submit">
          <Send size={16} />
          <span>{t("send")}</span>
        </button>
      </form>
    </section>
  );
}

function formatContext(value: unknown) {
  if (!value || typeof value !== "object") return "summary 0 · snippets 0 · tables 0";
  const item = value as Record<string, unknown>;
  return `summary ${item.document_summaries ?? 0} · snippets ${item.snippets ?? 0} · tables ${item.known_tables ?? 0} · ${item.language ?? ""}`;
}
