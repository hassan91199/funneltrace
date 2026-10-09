import { describe, expect, it } from "vitest";

import { describeEvent, leadNames, mergeEvents, type TraceEvent } from "@/lib/trace";

const ev = (id: number, type: string, payload: Record<string, unknown> = {}, lead = "L1"): TraceEvent => ({
  id,
  type,
  lead_id: lead,
  payload,
  created_at: "2026-01-01T10:00:00Z",
});

describe("mergeEvents", () => {
  it("keeps events ordered by id and ignores ones it already has", () => {
    const merged = mergeEvents([ev(1, "a"), ev(3, "c")], [ev(2, "b"), ev(3, "c"), ev(4, "d")]);
    expect(merged.map((e) => e.id)).toEqual([1, 2, 3, 4]);
  });

  it("returns the same array when nothing is new", () => {
    const current = [ev(1, "a")];
    expect(mergeEvents(current, [ev(1, "a")])).toBe(current);
  });
});

describe("describeEvent", () => {
  it("explains scoring with category, confidence and reasoning", () => {
    const d = describeEvent(ev(1, "scored", { category: "hot", confidence: 0.92, reasoning: "Urgent." }));
    expect(d.title).toBe("Scored hot (92%)");
    expect(d.detail).toBe("Urgent.");
    expect(d.tone).toBe("info");
  });

  it("says whether a lead was merged and why", () => {
    const merged = describeEvent(ev(2, "dedup_decision", { is_new: false, match_reason: "same phone" }));
    expect(merged.title).toBe("Merged into existing lead");
    expect(merged.detail).toBe("same phone");
    expect(describeEvent(ev(3, "dedup_decision", { is_new: true, match_reason: null })).title).toBe("New lead");
  });

  it("shows the CRM write and flags failures", () => {
    const ok = describeEvent(
      ev(4, "crm_synced", { crm: "hubspot", action: "create", external_id: "501", lifecycle_stage: "salesqualifiedlead" }),
    );
    expect(ok.title).toBe("CRM write: hubspot create");
    expect(ok.detail).toContain("501");
    expect(ok.detail).toContain("salesqualifiedlead");
    expect(ok.tone).toBe("success");
    const bad = describeEvent(ev(5, "crm_failed", { crm: "hubspot", error: "HubSpot 401" }));
    expect(bad.tone).toBe("error");
    expect(bad.detail).toBe("HubSpot 401");
  });

  it("shows the would-send payload", () => {
    const d = describeEvent(ev(6, "would_send", { channel: "web_form", to: "a@x.co", subject: "Re: hi" }));
    expect(d.title).toBe("Would send via web_form to a@x.co");
    expect(d.detail).toBe("Re: hi");
  });

  it("falls back to the raw type for unknown events", () => {
    expect(describeEvent(ev(7, "something_new")).title).toBe("something_new");
  });
});

describe("leadNames", () => {
  it("maps lead ids to the name they arrived with", () => {
    const names = leadNames([ev(1, "lead_received", { name: "Sarah" }, "L1"), ev(2, "scored", {}, "L1")]);
    expect(names).toEqual({ L1: "Sarah" });
  });
});
