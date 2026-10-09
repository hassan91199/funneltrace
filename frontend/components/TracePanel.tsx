"use client";

import { useEffect, useRef, useState } from "react";

import { describeEvent, leadNames, type TraceEvent } from "@/lib/trace";

type Props = { events: TraceEvent[]; connected: boolean };

export function TracePanel({ events, connected }: Props) {
  const [leadId, setLeadId] = useState("");
  const names = leadNames(events);
  const shown = leadId ? events.filter((e) => e.lead_id === leadId) : events;
  const list = useRef<HTMLOListElement>(null);

  // Keep the newest event in view as the journey grows.
  useEffect(() => {
    if (list.current) list.current.scrollTop = list.current.scrollHeight;
  }, [shown.length, leadId]);

  return (
    <div className="trace">
      <div className="trace-bar">
        <span className={connected ? "status live" : "status"}>{connected ? "Live" : "Reconnecting…"}</span>
        <label>
          Lead
          <select value={leadId} onChange={(e) => setLeadId(e.target.value)}>
            <option value="">All leads</option>
            {Object.entries(names).map(([id, name]) => (
              <option key={id} value={id}>
                {name}
              </option>
            ))}
          </select>
        </label>
      </div>
      {shown.length === 0 ? (
        <p className="empty">No events yet. They appear here the moment a lead arrives.</p>
      ) : (
        <ol className="events" ref={list}>
          {shown.map((event) => {
            const d = describeEvent(event);
            return (
              <li key={event.id} className={`event ${d.tone}`}>
                <div className="event-head">
                  <span className="lead-name">{(event.lead_id && names[event.lead_id]) || ""}</span>
                  <time>{event.created_at ? new Date(event.created_at).toLocaleTimeString() : ""}</time>
                </div>
                <div className="event-title">{d.title}</div>
                {d.detail && <div className="event-detail">{d.detail}</div>}
              </li>
            );
          })}
        </ol>
      )}
    </div>
  );
}
