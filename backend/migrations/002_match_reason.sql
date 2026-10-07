-- Why an inbound message was attached to an existing lead; NULL when it created the lead.
ALTER TABLE lead_messages ADD COLUMN match_reason text;
