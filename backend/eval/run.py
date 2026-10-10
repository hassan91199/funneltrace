"""Opt-in real eval: the 10 locked leads through real OpenAI + the HubSpot sandbox + Postgres.

    FUNNELTRACE_TEST_DATABASE_URL=postgresql://... python -m eval.run [--keep-contacts]

Needs OPENAI_API_KEY and HUBSPOT_ACCESS_TOKEN (backend/.env is read). The database must be a
scratch one: its `public` schema is dropped and recreated so dedup is graded from empty.
Contacts the run creates in the HubSpot sandbox are deleted afterwards unless --keep-contacts.
Results land in eval/results/ as JSON (everything measured) and Markdown (for the README).
Nothing here runs in the default test suite.
"""

import argparse
import dataclasses
import json
import os
import sys
from datetime import UTC, datetime
from pathlib import Path

import psycopg

from eval.runner import aggregate, aggregate_markdown, run_eval, to_markdown
from eval.test_set import TEST_SET
from funneltrace.config import load_env
from funneltrace.crm import HubSpotCrm
from funneltrace.db import apply_migrations
from funneltrace.intake import normalize_phone
from funneltrace.openai_llm import OpenAILLM
from funneltrace.repository import PgLeadRepository

RESULTS = Path(__file__).resolve().parent / "results"


def require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"{name} is required for the real eval run")
    return value


def existing_contacts(crm: HubSpotCrm) -> list[str]:
    """Sandbox contacts that already match an eval lead: they would turn creates into updates."""
    found = []
    for event in TEST_SET:
        p = event["payload"]
        phone = p.get("phone") or p.get("from") or ""
        contact = {"email": p.get("email", ""), "phone": normalize_phone(phone) or ""}
        contact_id = crm.find_contact(contact)
        if contact_id:
            found.append(f"#{event['id']} {event['person']} (contact {contact_id})")
    return found


def one_run(args, models, crm, api_key, database_url):
    leftovers = existing_contacts(crm)
    if leftovers:
        sys.exit(
            "These eval leads already exist in the HubSpot sandbox and would skew the CRM "
            "grading; delete them and rerun:\n  " + "\n  ".join(leftovers)
        )
    with psycopg.connect(database_url, autocommit=True) as conn:
        conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    apply_migrations(database_url)

    llm = OpenAILLM(api_key, models["scorer"])
    writer = llm if models["drafter"] == models["scorer"] else OpenAILLM(api_key, models["drafter"])
    judge = OpenAILLM(api_key, models["judge"])
    started = datetime.now(UTC)
    report = run_eval(
        llm,
        judge,
        crm,
        PgLeadRepository(database_url),
        crm_state=crm.get_contact,
        draft_llm=writer,
    )

    created = sorted({e.crm_external_id for e in report.events if e.crm_external_id})
    if not args.keep_contacts:
        for contact_id in created:
            crm.delete_contact(contact_id)

    stamp = started.strftime("%Y%m%dT%H%M%SZ")
    data = {
        "started_at": started.isoformat(),
        "models": models,
        "summary": report.summary(),
        "events": [dataclasses.asdict(e) for e in report.events],
        "hubspot_contacts_created": created,
        "hubspot_contacts_deleted": not args.keep_contacts,
    }
    (RESULTS / f"eval-{stamp}.json").write_text(json.dumps(data, indent=2) + "\n")
    markdown = to_markdown(report, models)
    (RESULTS / f"eval-{stamp}.md").write_text(markdown)
    print(markdown)
    print(f"Wrote eval/results/eval-{stamp}.json and .md")
    return report, stamp


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--keep-contacts", action="store_true")
    parser.add_argument("--runs", type=int, default=1, help="repeat the whole eval N times")
    parser.add_argument("--draft-model", help="model that writes the drafts (default: scorer)")
    args = parser.parse_args()

    load_env()
    database_url = require("FUNNELTRACE_TEST_DATABASE_URL")
    api_key = require("OPENAI_API_KEY")
    scorer = os.environ.get("OPENAI_MODEL") or "gpt-4o-mini"
    models = {
        "scorer": scorer,
        "drafter": args.draft_model or os.environ.get("EVAL_DRAFT_MODEL") or scorer,
        # A different model from the drafter, so it does not grade its own writing.
        "judge": os.environ.get("EVAL_JUDGE_MODEL") or "gpt-4.1",
    }
    if models["judge"] == models["drafter"]:
        print("warning: the judge is the same model as the drafter", file=sys.stderr)

    crm = HubSpotCrm(require("HUBSPOT_ACCESS_TOKEN"))
    RESULTS.mkdir(exist_ok=True)
    reports, stamps = [], []
    for number in range(1, args.runs + 1):
        print(f"--- run {number} of {args.runs} ---")
        report, stamp = one_run(args, models, crm, api_key, database_url)
        reports.append(report)
        stamps.append(stamp)
    if args.runs > 1:
        agg = aggregate(reports)
        markdown = aggregate_markdown(agg, models)
        (RESULTS / f"eval-{stamps[0]}-x{args.runs}.md").write_text(markdown)
        (RESULTS / f"eval-{stamps[0]}-x{args.runs}.json").write_text(
            json.dumps({"models": models, "runs": stamps, "aggregate": agg}, indent=2) + "\n"
        )
        print(markdown)


if __name__ == "__main__":
    main()
