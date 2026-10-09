export type TraceEvent = {
  id: number;
  type: string;
  lead_id: string | null;
  payload: Record<string, unknown>;
  created_at: string | null;
};

export type Tone = "info" | "success" | "error" | "muted";

export type Description = { title: string; detail?: string; tone: Tone };

// Every event type the backend emits; EventSource needs each named type registered.
export const EVENT_TYPES = [
  "lead_received",
  "dedup_decision",
  "scored",
  "score_failed",
  "drafted",
  "draft_failed",
  "draft_approved",
  "draft_rejected",
  "would_send",
  "crm_synced",
  "crm_failed",
] as const;

export function mergeEvents(current: TraceEvent[], incoming: TraceEvent[]): TraceEvent[] {
  const seen = new Set(current.map((e) => e.id));
  const fresh = incoming.filter((e) => !seen.has(e.id));
  if (fresh.length === 0) return current;
  return [...current, ...fresh].sort((a, b) => a.id - b.id);
}

const text = (value: unknown): string => (value == null ? "" : String(value));

export function describeEvent(event: TraceEvent): Description {
  const p = event.payload;
  switch (event.type) {
    case "lead_received":
      return { title: `Lead received via ${text(p.channel)}`, detail: text(p.message), tone: "info" };
    case "dedup_decision":
      return p.is_new
        ? { title: "New lead", tone: "info" }
        : { title: "Merged into existing lead", detail: text(p.match_reason), tone: "info" };
    case "scored":
      return {
        title: `Scored ${text(p.category)} (${Math.round(Number(p.confidence) * 100)}%)`,
        detail: text(p.reasoning),
        tone: "info",
      };
    case "score_failed":
      return { title: "Scoring failed", detail: text(p.error), tone: "error" };
    case "drafted":
      return { title: "Follow-up drafted, awaiting approval", detail: text(p.subject), tone: "info" };
    case "draft_failed":
      return { title: "Drafting failed", detail: text(p.error), tone: "error" };
    case "draft_approved":
      return { title: "Draft approved", tone: "success" };
    case "draft_rejected":
      return { title: "Draft rejected", tone: "muted" };
    case "would_send":
      return {
        title: `Would send via ${text(p.channel)} to ${text(p.to)}`,
        detail: text(p.subject),
        tone: "success",
      };
    case "crm_synced":
      return {
        title: `CRM write: ${text(p.crm)} ${text(p.action)}`,
        detail: `contact ${text(p.external_id)} · ${text(p.lifecycle_stage)}`,
        tone: "success",
      };
    case "crm_failed":
      return { title: `CRM write failed: ${text(p.crm)}`, detail: text(p.error), tone: "error" };
    default:
      return { title: event.type, tone: "muted" };
  }
}

export function leadNames(events: TraceEvent[]): Record<string, string> {
  const names: Record<string, string> = {};
  for (const e of events) {
    if (e.type === "lead_received" && e.lead_id && !(e.lead_id in names)) {
      names[e.lead_id] = text(e.payload.name);
    }
  }
  return names;
}
