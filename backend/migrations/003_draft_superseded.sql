-- A newer draft for the same lead replaces an undecided one; keep it for the audit trail.
ALTER TABLE drafts DROP CONSTRAINT drafts_status_check;
ALTER TABLE drafts ADD CONSTRAINT drafts_status_check
    CHECK (status IN ('pending', 'approved', 'rejected', 'superseded'));
