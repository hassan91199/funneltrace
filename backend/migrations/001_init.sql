CREATE TABLE leads (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    name text NOT NULL,
    email text,
    phone text,
    normalized_email text,
    normalized_phone text,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX leads_normalized_email_idx ON leads (normalized_email);
CREATE INDEX leads_normalized_phone_idx ON leads (normalized_phone);

-- One row per inbound contact; a deduped lead can have several, across channels.
CREATE TABLE lead_messages (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id uuid NOT NULL REFERENCES leads (id) ON DELETE CASCADE,
    channel text NOT NULL CHECK (channel IN ('web_form', 'whatsapp')),
    body text NOT NULL,
    raw_payload jsonb NOT NULL,
    received_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX lead_messages_lead_idx ON lead_messages (lead_id);

CREATE TABLE scoring_history (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id uuid NOT NULL REFERENCES leads (id) ON DELETE CASCADE,
    category text NOT NULL CHECK (category IN ('hot', 'warm', 'cold')),
    confidence real NOT NULL CHECK (confidence >= 0 AND confidence <= 1),
    reasoning text NOT NULL,
    model text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX scoring_history_lead_idx ON scoring_history (lead_id);

CREATE TABLE drafts (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id uuid NOT NULL REFERENCES leads (id) ON DELETE CASCADE,
    scoring_id uuid REFERENCES scoring_history (id),
    subject text NOT NULL,
    body text NOT NULL,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'approved', 'rejected')),
    created_at timestamptz NOT NULL DEFAULT now(),
    decided_at timestamptz
);
CREATE INDEX drafts_status_idx ON drafts (status);

CREATE TABLE crm_syncs (
    id uuid PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id uuid NOT NULL REFERENCES leads (id) ON DELETE CASCADE,
    draft_id uuid REFERENCES drafts (id),
    crm text NOT NULL,
    external_id text,
    status text NOT NULL CHECK (status IN ('synced', 'failed')),
    error text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE trace_events (
    id bigserial PRIMARY KEY,
    lead_id uuid REFERENCES leads (id) ON DELETE CASCADE,
    type text NOT NULL,
    payload jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX trace_events_lead_idx ON trace_events (lead_id, id);
