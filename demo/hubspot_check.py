"""Check, then remove, the sandbox contacts the demo run created.

Run from backend/ so .env is found:
    PYTHONPATH=. python ../demo/hubspot_check.py [--delete]
Reads the external ids from the demo database (DATABASE_URL).
"""
import os
import sys

import psycopg

from funneltrace.config import Settings, load_env
from funneltrace.crm import HubSpotCrm

load_env()
crm = HubSpotCrm(os.environ["HUBSPOT_ACCESS_TOKEN"])
with psycopg.connect(Settings.from_env().database_url) as conn:
    rows = conn.execute(
        "SELECT external_id, action FROM crm_syncs WHERE status = 'synced'"
    ).fetchall()
for external_id, action in rows:
    print(external_id, action, crm.get_contact(external_id))
    if "--delete" in sys.argv:
        crm.delete_contact(external_id)
        print("  deleted")
print(f"{len(rows)} synced contact(s)")
