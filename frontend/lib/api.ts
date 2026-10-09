export const API_URL = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Draft = {
  id: string;
  lead_id: string;
  lead_name: string;
  category: "hot" | "warm" | "cold" | null;
  confidence: number | null;
  reasoning: string | null;
  subject: string;
  body: string;
  status: "pending" | "approved" | "rejected" | "superseded";
  created_at: string;
  decided_at: string | null;
};

export type Channel = "web_form" | "whatsapp";

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, init);
  if (!response.ok) {
    let detail = `${response.status} ${response.statusText}`;
    try {
      const body = await response.json();
      if (typeof body.detail === "string") detail = body.detail;
    } catch {
      // keep the status line
    }
    throw new Error(detail);
  }
  return response.json() as Promise<T>;
}

export const listPendingDrafts = () => request<Draft[]>("/drafts?status=pending");

export const decideDraft = (id: string, decision: "approve" | "reject") =>
  request<unknown>(`/drafts/${id}/${decision}`, { method: "POST" });

export const sendLead = (channel: Channel, payload: Record<string, string>) =>
  request<unknown>(channel === "web_form" ? "/webhooks/web-form" : "/webhooks/whatsapp", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
