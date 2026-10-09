import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { Inbox } from "@/components/Inbox";
import type { Draft } from "@/lib/api";

const draft: Draft = {
  id: "d1",
  lead_id: "L1",
  lead_name: "Sarah Mitchell",
  category: "hot",
  confidence: 0.92,
  reasoning: "Urgent furnace outage with budget.",
  subject: "Re: your furnace",
  body: "We can visit this week.",
  status: "pending",
  created_at: "2026-01-01T10:00:00Z",
  decided_at: null,
};

describe("Inbox", () => {
  it("shows who, how hot, how sure, why, and the draft text", () => {
    render(<Inbox drafts={[draft]} onDecide={vi.fn()} />);
    expect(screen.getByText("Sarah Mitchell")).toBeInTheDocument();
    expect(screen.getByText("hot")).toBeInTheDocument();
    expect(screen.getByText("92% confident")).toBeInTheDocument();
    expect(screen.getByText("Urgent furnace outage with budget.")).toBeInTheDocument();
    expect(screen.getByText("Re: your furnace")).toBeInTheDocument();
    expect(screen.getByText("We can visit this week.")).toBeInTheDocument();
  });

  it("approves and rejects by draft id", async () => {
    const onDecide = vi.fn().mockResolvedValue(undefined);
    render(<Inbox drafts={[draft]} onDecide={onDecide} />);
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(onDecide).toHaveBeenCalledWith("d1", "approve");
    await userEvent.click(screen.getByRole("button", { name: "Reject" }));
    expect(onDecide).toHaveBeenCalledWith("d1", "reject");
  });

  it("explains an empty inbox", () => {
    render(<Inbox drafts={[]} onDecide={vi.fn()} />);
    expect(screen.getByText(/no drafts waiting/i)).toBeInTheDocument();
  });

  it("surfaces a failed decision instead of hiding it", async () => {
    const onDecide = vi.fn().mockRejectedValue(new Error("draft is already decided"));
    render(<Inbox drafts={[draft]} onDecide={onDecide} />);
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    expect(await screen.findByText("draft is already decided")).toBeInTheDocument();
  });
});
