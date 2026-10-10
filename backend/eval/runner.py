"""The eval harness: feeds the locked events through the real app, in order, and grades each.

Per event it grades four things: category, dedup, draft relevance and the CRM write. The app
is driven in process through its public webhook and approval endpoints, so the LLM, CRM and
repository are whatever the caller injects: fakes in the default suite (tests/test_eval_runner.py),
real OpenAI + HubSpot sandbox + Postgres in the opt-in run (`python -m eval.run`).

Every figure in a report is measured here; nothing is estimated.
"""

import statistics
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from fastapi.testclient import TestClient

from eval.test_set import TEST_SET
from funneltrace.api import create_app

JUDGE_SYSTEM = """\
You grade a drafted reply to an inbound lead for a small home-services company. You are given \
the conversation and a checklist. For every checklist point, decide whether the draft \
satisfies it.

Be strict. A point is met only if the draft clearly does it, and you must back every met \
point with "evidence": one single contiguous quote, copied word for word from the draft (never \
two passages joined together). If you cannot quote words that show it, the point is not met \
and the evidence is an empty string. Points that say the draft "does not" do something are \
met by absence: they need no quote (use an empty string); they are not met only if the draft \
does it, and then quote the offending words. Generic \
politeness ("thanks for reaching out", "happy to help") does not show that a draft refers to \
something specific; a point about an earlier message or a stated detail needs a specific \
reference to that content. Judge the draft, not the lead. Return every point exactly as \
written.
"""

JUDGE_SCHEMA = {
    "type": "object",
    "properties": {
        "points": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "point": {"type": "string"},
                    "met": {"type": "boolean"},
                    "evidence": {"type": "string"},
                    "why": {"type": "string"},
                },
                "required": ["point", "met", "evidence", "why"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["points"],
    "additionalProperties": False,
}

# "does not ..." points are met by absence, so there are no words to quote for them.
NEGATIVE_POINTS = ("does not", "do not", "never")

WEBHOOK = {"web_form": "/webhooks/web-form", "whatsapp": "/webhooks/whatsapp"}


@dataclass
class EventResult:
    id: int
    person: str
    channel: str
    expected_category: str
    expected_new_lead: bool
    expected_crm: dict
    lead_id: str | None = None
    got_category: str | None = None
    confidence: float | None = None
    reasoning: str | None = None
    is_new: bool | None = None
    match_reason: str | None = None
    draft_subject: str | None = None
    draft_body: str | None = None
    judge: list[dict] = field(default_factory=list)
    judge_error: str | None = None
    crm_status: str | None = None
    crm_action: str | None = None
    crm_stage: str | None = None
    crm_external_id: str | None = None
    crm_error: str | None = None
    crm_state: dict | None = None
    category_ok: bool = False
    dedup_ok: bool = False
    draft_ok: bool = False
    crm_ok: bool = False
    webhook_s: float = 0.0
    approve_s: float = 0.0

    @property
    def all_ok(self) -> bool:
        return self.category_ok and self.dedup_ok and self.draft_ok and self.crm_ok


@dataclass
class EvalReport:
    events: list[EventResult]

    def summary(self) -> dict:
        def stats(values: list[float]) -> dict:
            return {
                "mean": statistics.fmean(values),
                "p50": statistics.median(values),
                "max": max(values),
            }

        webhook = [e.webhook_s for e in self.events]
        approve = [e.approve_s for e in self.events]
        return {
            "events": len(self.events),
            "passed": {
                "category": sum(e.category_ok for e in self.events),
                "dedup": sum(e.dedup_ok for e in self.events),
                "draft": sum(e.draft_ok for e in self.events),
                "crm": sum(e.crm_ok for e in self.events),
            },
            "all_passed": sum(e.all_ok for e in self.events),
            "distinct_leads": len({e.lead_id for e in self.events if e.lead_id}),
            "latency_s": {
                "webhook": stats(webhook),
                "approve": stats(approve),
                "total": stats([a + b for a, b in zip(webhook, approve, strict=True)]),
            },
        }


def _squash(text: str) -> str:
    # Curly quotes in a quote must not break an exact-substring check.
    text = text.replace("\u2019", "'").replace("\u201c", '"').replace("\u201d", '"')
    return " ".join(text.lower().split())


def judge_draft(judge, event: dict, messages: list[tuple[str, str]], subject: str, body: str):
    """Ask the judge whether each checklist point is met. Returns (points, error)."""
    checklist = event["draft_must_address"]
    conversation = "\n".join(f"[{channel}] {text}" for channel, text in messages)
    user = (
        f"Conversation:\n{conversation}\n\nDrafted reply:\nSubject: {subject}\n{body}\n\n"
        "Checklist:\n" + "\n".join(f"- {point}" for point in checklist)
    )
    try:
        raw = judge.complete_json(JUDGE_SYSTEM, user, JUDGE_SCHEMA)
        verdicts = {p["point"]: p for p in raw["points"]}
        draft_text = _squash(f"{subject} {body}")
        points = []
        for point in checklist:
            verdict = verdicts[point]
            met, why = bool(verdict["met"]), verdict["why"]
            quote = verdict.get("evidence", "")
            # A claim without words from the draft behind it does not count.
            needs_quote = not point.lower().startswith(NEGATIVE_POINTS)
            if met and needs_quote and (not quote.strip() or _squash(quote) not in draft_text):
                met, why = False, f"quoted evidence not found in the draft ({quote!r})"
            points.append({"point": point, "met": met, "evidence": quote, "why": why})
    except Exception as exc:  # a judge that fails to answer must not read as a pass
        return [{"point": p, "met": False, "why": "not judged"} for p in checklist], str(exc)
    return points, None


def run_eval(
    llm,
    judge,
    crm,
    repo,
    events: list[dict] = TEST_SET,
    crm_state: Callable[[str], dict] | None = None,
    clock: Callable[[], float] = time.perf_counter,
) -> EvalReport:
    client = TestClient(create_app(repo=repo, llm=llm, crm=crm))
    first_lead: dict[str, str] = {}  # person -> lead id of their first event
    results: list[EventResult] = []

    for event in events:
        result = EventResult(
            id=event["id"],
            person=event["person"],
            channel=event["channel"],
            expected_category=event["expected_category"],
            expected_new_lead=event["expect_new_lead"],
            expected_crm=event["expected_crm"],
        )
        results.append(result)

        start = clock()
        response = client.post(WEBHOOK[event["channel"]], json=event["payload"])
        result.webhook_s = clock() - start
        body = response.json()
        if response.status_code != 201:
            continue
        result.lead_id = body["lead_id"]
        result.is_new, result.match_reason = body["is_new"], body["match_reason"]
        first_lead.setdefault(event["person"], result.lead_id)

        if body.get("score"):
            result.got_category = body["score"]["category"]
            result.confidence = body["score"]["confidence"]
            result.reasoning = body["score"]["reasoning"]
        result.category_ok = result.got_category == event["expected_category"]

        draft = body.get("draft")
        if not draft:
            continue
        result.draft_subject, result.draft_body = draft["subject"], draft["body"]
        messages = repo.get_context(result.lead_id).messages
        result.judge, result.judge_error = judge_draft(
            judge, event, messages, draft["subject"], draft["body"]
        )
        result.draft_ok = all(p["met"] for p in result.judge)

        start = clock()
        approved = client.post(f"/drafts/{draft['id']}/approve").json()
        result.approve_s = clock() - start
        sync = approved.get("crm") or {}
        result.crm_status, result.crm_action = sync.get("status"), sync.get("action")
        result.crm_external_id, result.crm_error = sync.get("external_id"), sync.get("error")
        synced = [e for e in repo.events_for(result.lead_id) if e.type == "crm_synced"]
        if synced:
            result.crm_stage = synced[-1].payload.get("lifecycle_stage")

        expected = event["expected_crm"]
        result.crm_ok = (
            result.crm_status == "synced"
            and result.crm_action == expected["action"]
            and result.crm_stage == expected["lifecycle_stage"]
        )
        if crm_state and result.crm_external_id:
            result.crm_state = crm_state(result.crm_external_id)
            result.crm_ok = result.crm_ok and (
                result.crm_state.get("lifecyclestage") == expected["lifecycle_stage"]
            )

    # Dedup is graded against the whole stream: right new/merged call AND the same person
    # always lands on one lead while different people never share one.
    owner = {lead: person for person, lead in first_lead.items()}
    for result in results:
        result.dedup_ok = (
            result.lead_id is not None
            and result.is_new is result.expected_new_lead
            and first_lead.get(result.person) == result.lead_id
            and owner.get(result.lead_id) == result.person
        )
    return EvalReport(results)


def to_markdown(report: EvalReport, models: dict[str, str]) -> str:
    s = report.summary()
    n = s["events"]
    lat = s["latency_s"]
    mark = {True: "pass", False: "FAIL"}
    lines = [
        "| # | channel | category (expected → got) | dedup | draft | CRM (expected → got) "
        "| latency s |",
        "|---|---|---|---|---|---|---|",
    ]
    for e in report.events:
        unmet = [p["point"] for p in e.judge if not p["met"]]
        draft = mark[e.draft_ok] + (f" (unmet: {'; '.join(unmet)})" if unmet else "")
        exp = e.expected_crm
        crm = (
            f"{exp['action']}/{exp['lifecycle_stage']} → "
            f"{e.crm_action or e.crm_error or 'none'}/{e.crm_stage or '-'}"
        )
        lines.append(
            f"| {e.id} | {e.channel} | {e.expected_category} → {e.got_category or 'none'} "
            f"{mark[e.category_ok]} | {mark[e.dedup_ok]} | {draft} | {mark[e.crm_ok]}: {crm} "
            f"| {e.webhook_s + e.approve_s:.1f} |"
        )
    p = s["passed"]
    summary = [
        f"Models: scorer/drafter `{models['scorer']}`, draft judge `{models['judge']}`.",
        "",
        f"- Category correct: {p['category']}/{n}",
        f"- Dedup correct: {p['dedup']}/{n} ({s['distinct_leads']} distinct leads)",
        f"- Draft relevant (LLM-judged, every checklist point met): {p['draft']}/{n}",
        f"- CRM write correct: {p['crm']}/{n}",
        f"- Events passing all four: {s['all_passed']}/{n}",
        "",
        "Latency per event, seconds (n="
        f"{n}): intake to scored and drafted: mean {lat['webhook']['mean']:.1f}, "
        f"median {lat['webhook']['p50']:.1f}, max {lat['webhook']['max']:.1f}; "
        f"approval including the HubSpot write: mean {lat['approve']['mean']:.1f}, "
        f"median {lat['approve']['p50']:.1f}, max {lat['approve']['max']:.1f}.",
        "",
    ]
    return "\n".join(summary + lines) + "\n"
