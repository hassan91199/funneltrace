import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";

import { TracePanel } from "@/components/TracePanel";
import type { TraceEvent } from "@/lib/trace";

const ev = (id: number, type: string, lead: string, payload: Record<string, unknown> = {}): TraceEvent => ({
  id,
  type,
  lead_id: lead,
  payload,
  created_at: "2026-01-01T10:00:00Z",
});

const events = [
  ev(1, "lead_received", "A", { name: "Sarah", channel: "web_form", message: "furnace" }),
  ev(2, "lead_received", "B", { name: "Priya", channel: "whatsapp", message: "tune up" }),
  ev(3, "scored", "A", { category: "hot", confidence: 0.9, reasoning: "Urgent." }),
  ev(4, "crm_synced", "A", { crm: "hubspot", action: "create", external_id: "501", lifecycle_stage: "salesqualifiedlead" }),
];

describe("TracePanel", () => {
  it("lists every lead's events with the lead's name, in order", () => {
    render(<TracePanel events={events} connected />);
    const rows = screen.getAllByRole("listitem");
    expect(rows).toHaveLength(4);
    expect(within(rows[0]).getByText("Sarah")).toBeInTheDocument();
    expect(within(rows[3]).getByText("CRM write: hubspot create")).toBeInTheDocument();
  });

  it("narrows to one lead's journey and back", async () => {
    render(<TracePanel events={events} connected />);
    await userEvent.selectOptions(screen.getByLabelText("Lead"), "B");
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByText("tune up")).toBeInTheDocument();
    await userEvent.selectOptions(screen.getByLabelText("Lead"), "");
    expect(screen.getAllByRole("listitem")).toHaveLength(4);
  });

  it("shows whether the live stream is connected", () => {
    const { rerender } = render(<TracePanel events={[]} connected />);
    expect(screen.getByText("Live")).toBeInTheDocument();
    rerender(<TracePanel events={[]} connected={false} />);
    expect(screen.getByText("Reconnecting…")).toBeInTheDocument();
  });
});
