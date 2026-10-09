"use client";

import { useCallback, useEffect, useRef, useState } from "react";

import { DemoLeads } from "@/components/DemoLeads";
import { Inbox } from "@/components/Inbox";
import { TracePanel } from "@/components/TracePanel";
import { decideDraft, listPendingDrafts, sendLead, type Draft } from "@/lib/api";
import type { TraceEvent } from "@/lib/trace";
import { useTrace } from "@/lib/useTrace";

const INBOX_CHANGING = new Set(["drafted", "draft_approved", "draft_rejected"]);

export default function Home() {
  const [drafts, setDrafts] = useState<Draft[]>([]);
  const [loadError, setLoadError] = useState("");
  const refreshing = useRef(false);

  const refresh = useCallback(async () => {
    if (refreshing.current) return;
    refreshing.current = true;
    try {
      setDrafts(await listPendingDrafts());
      setLoadError("");
    } catch (error) {
      setLoadError(error instanceof Error ? error.message : String(error));
    } finally {
      refreshing.current = false;
    }
  }, []);

  // The trace stream is the single source of "something changed": the inbox follows it.
  const onEvent = useCallback(
    (event: TraceEvent) => {
      if (INBOX_CHANGING.has(event.type)) void refresh();
    },
    [refresh],
  );
  const { events, connected } = useTrace(onEvent);

  useEffect(() => {
    let active = true;
    listPendingDrafts()
      .then((loaded) => active && setDrafts(loaded))
      .catch((error) => active && setLoadError(error instanceof Error ? error.message : String(error)));
    return () => {
      active = false;
    };
  }, []);

  return (
    <main className="layout">
      <header className="top">
        <h1>FunnelTrace</h1>
        <p>Leads in, scored and drafted by the model, sent nowhere until a human approves.</p>
      </header>
      <section className="col">
        <h2>Approval inbox</h2>
        {loadError && <p className="error">Could not load drafts: {loadError}</p>}
        <Inbox
          drafts={drafts}
          onDecide={async (id, decision) => {
            await decideDraft(id, decision);
            await refresh();
          }}
        />
      </section>
      <section className="col">
        <h2>Live trace</h2>
        <TracePanel events={events} connected={connected} />
      </section>
      <section className="col">
        <h2>Fire a demo lead</h2>
        <DemoLeads onSend={async (channel, payload) => void (await sendLead(channel, payload))} />
      </section>
    </main>
  );
}
