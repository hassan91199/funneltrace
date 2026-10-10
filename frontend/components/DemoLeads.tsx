"use client";

import { useState } from "react";

import type { Channel } from "@/lib/api";

export type Preset = {
  label: string;
  channel: Channel;
  payload: Record<string, string>;
};

// Drawn from the eval set. Send "Sarah, form" before "Sarah, WhatsApp" to see a cross-channel merge.
export const PRESETS: Preset[] = [
  {
    label: "Hot: Sarah, form (furnace out)",
    channel: "web_form",
    payload: {
      name: "Sarah Mitchell",
      email: "sarah.mitchell@example.com",
      phone: "+1 (415) 555-0142",
      message:
        "Our furnace died last night and it's freezing. I need a replacement quote this week. Budget is approved up to $9k.",
    },
  },
  {
    label: "Same person: Sarah, WhatsApp (merges)",
    channel: "whatsapp",
    payload: {
      from: "14155550142",
      profile_name: "Sarah M",
      text: "Hi, I sent a form earlier. Can someone call me today? The furnace is out and the house is cold.",
    },
  },
  {
    label: "Warm: Daniel, form (remodel)",
    channel: "web_form",
    payload: {
      name: "Daniel Okafor",
      email: "d.okafor@example.com",
      phone: "+1 650 555 0177",
      message:
        "Planning a kitchen remodel in about three months. Would like a ballpark and to understand how your process works.",
    },
  },
  {
    label: "Warm: Priya, WhatsApp (AC tune-up)",
    channel: "whatsapp",
    payload: { from: "923005550188", profile_name: "Priya", text: "hi how much for an AC tune up?" },
  },
  {
    label: "Cold: Jason, form (SEO vendor)",
    channel: "web_form",
    payload: {
      name: "Jason Lee",
      email: "jason.lee@example.com",
      phone: "+1 305 555 0110",
      message: "We can get your company onto page 1 of Google in 30 days. Reply for a free audit.",
    },
  },
  {
    label: "Hot: Ahmed, WhatsApp (burst pipe)",
    channel: "whatsapp",
    payload: {
      from: "447700900123",
      profile_name: "Ahmed Raza",
      text: "Water pipe burst in my basement, need a plumber ASAP. I'll pay the emergency rate, please come now.",
    },
  },
];

type Props = { onSend: (channel: Channel, payload: Record<string, string>) => Promise<void> };

export function DemoLeads({ onSend }: Props) {
  const [sending, setSending] = useState(false);
  const [error, setError] = useState("");
  const [channel, setChannel] = useState<Channel>("web_form");
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const [message, setMessage] = useState("");

  async function send(ch: Channel, payload: Record<string, string>) {
    setSending(true);
    setError("");
    try {
      await onSend(ch, payload);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSending(false);
    }
  }

  function sendCustom(event: React.FormEvent) {
    event.preventDefault();
    return send(
      channel,
      channel === "web_form"
        ? { name, email, phone, message }
        : { from: phone, profile_name: name, text: message },
    );
  }

  return (
    <div className="demo">
      <div className="presets">
        {PRESETS.map((preset) => (
          <button key={preset.label} disabled={sending} onClick={() => send(preset.channel, preset.payload)}>
            {preset.label}
          </button>
        ))}
      </div>
      <form onSubmit={sendCustom}>
        <label>
          Channel
          <select value={channel} onChange={(e) => setChannel(e.target.value as Channel)}>
            <option value="web_form">Web form</option>
            <option value="whatsapp">WhatsApp</option>
          </select>
        </label>
        <label>
          Name
          <input value={name} onChange={(e) => setName(e.target.value)} />
        </label>
        {channel === "web_form" && (
          <label>
            Email
            <input value={email} onChange={(e) => setEmail(e.target.value)} />
          </label>
        )}
        <label>
          Phone
          <input value={phone} onChange={(e) => setPhone(e.target.value)} />
        </label>
        <label>
          Message
          <textarea value={message} onChange={(e) => setMessage(e.target.value)} rows={3} />
        </label>
        <button type="submit" disabled={sending}>
          Send custom lead
        </button>
      </form>
      {error && <p className="error">{error}</p>}
    </div>
  );
}
