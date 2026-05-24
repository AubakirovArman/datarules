import { RefreshCw, ShieldCheck } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@shared/api";
import type { AuditEvent } from "@shared/types";

type Props = {
  t: (key: string) => string;
};

export function AuditTrail({ t }: Props) {
  const [events, setEvents] = useState<AuditEvent[]>([]);
  const [busy, setBusy] = useState(false);

  async function refresh() {
    setBusy(true);
    try {
      setEvents(await api.auditEvents());
    } finally {
      setBusy(false);
    }
  }

  useEffect(() => {
    refresh();
  }, []);

  return (
    <div className="audit-trail">
      <div className="audit-head">
        <strong><ShieldCheck size={15} /> {t("auditTrail")}</strong>
        <button className="icon-button" disabled={busy} onClick={refresh} title={t("refresh")}>
          <RefreshCw size={14} />
        </button>
      </div>
      {events.length === 0 && <small>{t("noAuditEvents")}</small>}
      {events.slice(0, 12).map((event) => (
        <article className="audit-event" key={event.id}>
          <span>{event.action}</span>
          <small>{target(event)} · {time(event.created_at)}</small>
        </article>
      ))}
    </div>
  );
}

function target(event: AuditEvent) {
  return [event.entity_type, event.entity_id].filter(Boolean).join(":") || event.actor;
}

function time(value?: string | null) {
  if (!value) return "";
  return new Date(value).toLocaleString();
}
