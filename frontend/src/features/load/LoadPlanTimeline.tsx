import type { LoadPlan } from "@shared/types";

type Props = {
  events: LoadPlan["events"];
};

export function LoadPlanTimeline({ events }: Props) {
  if (!events?.length) return null;
  return (
    <div className="load-timeline">
      {events.slice(-6).map((event) => (
        <div className="load-timeline-item" key={event.id}>
          <strong>{event.action}</strong>
          <span>{event.message}</span>
          <small>{new Date(event.created_at).toLocaleString()}</small>
        </div>
      ))}
    </div>
  );
}
