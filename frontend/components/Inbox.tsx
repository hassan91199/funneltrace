"use client";

import { useState } from "react";

import type { Draft } from "@/lib/api";

type Props = {
  drafts: Draft[];
  onDecide: (id: string, decision: "approve" | "reject") => Promise<void>;
};

export function Inbox({ drafts, onDecide }: Props) {
  const [busy, setBusy] = useState<string | null>(null);
  const [errors, setErrors] = useState<Record<string, string>>({});

  async function decide(id: string, decision: "approve" | "reject") {
    setBusy(id);
    setErrors((prev) => Object.fromEntries(Object.entries(prev).filter(([key]) => key !== id)));
    try {
      await onDecide(id, decision);
    } catch (error) {
      setErrors((prev) => ({ ...prev, [id]: error instanceof Error ? error.message : String(error) }));
    } finally {
      setBusy(null);
    }
  }

  if (drafts.length === 0) {
    return <p className="empty">No drafts waiting for approval. Fire a demo lead to get one.</p>;
  }

  return (
    <ul className="cards">
      {drafts.map((draft) => (
        <li key={draft.id} className="card">
          <header>
            <strong>{draft.lead_name}</strong>
            {draft.category && <span className={`badge ${draft.category}`}>{draft.category}</span>}
            {draft.confidence != null && (
              <span className="muted">{Math.round(draft.confidence * 100)}% confident</span>
            )}
          </header>
          {draft.reasoning && <p className="reasoning">{draft.reasoning}</p>}
          <div className="draft">
            <div className="subject">{draft.subject}</div>
            <div className="body">{draft.body}</div>
          </div>
          {errors[draft.id] && <p className="error">{errors[draft.id]}</p>}
          <footer>
            <button className="approve" disabled={busy === draft.id} onClick={() => decide(draft.id, "approve")}>
              Approve
            </button>
            <button className="reject" disabled={busy === draft.id} onClick={() => decide(draft.id, "reject")}>
              Reject
            </button>
          </footer>
        </li>
      ))}
    </ul>
  );
}
