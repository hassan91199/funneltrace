import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { DemoLeads, PRESETS } from "@/components/DemoLeads";

describe("DemoLeads", () => {
  it("covers both channels, including a same-person follow-up to show dedup", () => {
    const channels = new Set(PRESETS.map((p) => p.channel));
    expect(channels).toEqual(new Set(["web_form", "whatsapp"]));
    expect(PRESETS.length).toBeGreaterThanOrEqual(4);
  });

  it("fires a preset lead on its channel", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    render(<DemoLeads onSend={onSend} />);
    const preset = PRESETS[0];
    await userEvent.click(screen.getByRole("button", { name: preset.label }));
    expect(onSend).toHaveBeenCalledWith(preset.channel, preset.payload);
  });

  it("sends a custom web form lead", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    render(<DemoLeads onSend={onSend} />);
    await userEvent.type(screen.getByLabelText("Name"), "Dana");
    await userEvent.type(screen.getByLabelText("Email"), "dana@x.co");
    await userEvent.type(screen.getByLabelText("Message"), "Need a quote");
    await userEvent.click(screen.getByRole("button", { name: "Send custom lead" }));
    expect(onSend).toHaveBeenCalledWith("web_form", {
      name: "Dana",
      email: "dana@x.co",
      phone: "",
      message: "Need a quote",
    });
  });

  it("sends a custom WhatsApp lead with the webhook's field names", async () => {
    const onSend = vi.fn().mockResolvedValue(undefined);
    render(<DemoLeads onSend={onSend} />);
    await userEvent.selectOptions(screen.getByLabelText("Channel"), "whatsapp");
    await userEvent.type(screen.getByLabelText("Phone"), "14155550100");
    await userEvent.type(screen.getByLabelText("Name"), "Lee");
    await userEvent.type(screen.getByLabelText("Message"), "hello");
    await userEvent.click(screen.getByRole("button", { name: "Send custom lead" }));
    expect(onSend).toHaveBeenCalledWith("whatsapp", {
      from: "14155550100",
      profile_name: "Lee",
      text: "hello",
    });
  });
});
