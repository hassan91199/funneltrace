"use client";

import { useEffect, useState } from "react";

import { API_URL } from "@/lib/api";
import { EVENT_TYPES, mergeEvents, type TraceEvent } from "@/lib/trace";

/** Replays the stored trace, then follows it live. The browser resumes a dropped stream by
 * itself via Last-Event-ID, and mergeEvents ignores anything already seen. */
export function useTrace(onEvent?: (event: TraceEvent) => void) {
  const [events, setEvents] = useState<TraceEvent[]>([]);
  const [connected, setConnected] = useState(false);

  useEffect(() => {
    const source = new EventSource(`${API_URL}/events`);
    const handle = (message: MessageEvent) => {
      const event = JSON.parse(message.data) as TraceEvent;
      setEvents((current) => mergeEvents(current, [event]));
      onEvent?.(event);
    };
    source.onopen = () => setConnected(true);
    source.onerror = () => setConnected(false);
    for (const type of EVENT_TYPES) source.addEventListener(type, handle as EventListener);
    return () => source.close();
    // onEvent is read through a ref-like closure at call time; reconnecting on its identity would
    // drop the stream on every render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { events, connected };
}
