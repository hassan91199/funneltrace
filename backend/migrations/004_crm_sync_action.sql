-- Whether the sync created a new CRM contact or updated an existing one.
ALTER TABLE crm_syncs ADD COLUMN action text CHECK (action IN ('create', 'update'));
