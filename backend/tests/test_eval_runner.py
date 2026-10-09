"""The eval harness itself, exercised offline with fakes. The real run is `python -m eval.run`."""

from eval.runner import run_eval, to_markdown
from eval.test_set import TEST_SET
from funneltrace.interfaces import CrmError, LLMRefusal
from funneltrace.repository import InMemoryLeadRepository
from tests.fakes import FakeCrm, FakeLLM

PERFECT_SCORES = [
    {"category": e["expected_category"], "confidence": 0.9, "reasoning": f"r{e['id']}"}
    for e in TEST_SET
]
DRAFTS = [{"subject": f"Re {e['id']}", "body": f"Body {e['id']}"} for e in TEST_SET]


class StubJudge:
    """Reads the checklist lines out of the prompt; marks `unmet` ones as not satisfied."""

    model = "stub-judge"

    def __init__(self, unmet=()):
        self.unmet = set(unmet)
        self.calls = 0

    def complete_json(self, system, user, schema):
        self.calls += 1
        points = [line[2:] for line in user.splitlines() if line.startswith("- ")]
        return {"points": [{"point": p, "met": p not in self.unmet, "why": "stub"} for p in points]}


def run(scores=None, drafts=None, judge=None, crm=None, **kw):
    # FakeLLM consumes the lists it is given, so each run gets its own copies.
    llm = FakeLLM(score=list(scores or PERFECT_SCORES), draft=list(drafts or DRAFTS))
    return run_eval(
        llm=llm,
        judge=judge or StubJudge(),
        crm=crm or FakeCrm(),
        repo=InMemoryLeadRepository(),
        **kw,
    )


def test_a_perfect_pipeline_passes_every_check_on_every_event():
    report = run()
    assert [e.id for e in report.events] == list(range(1, 11))
    for event in report.events:
        assert event.all_ok, event
    summary = report.summary()
    assert summary["events"] == 10
    for check in ("category", "dedup", "draft", "crm"):
        assert summary["passed"][check] == 10
    assert summary["all_passed"] == 10
    assert summary["distinct_leads"] == 7


def test_a_wrong_category_fails_only_that_event():
    scores = [dict(s) for s in PERFECT_SCORES]
    scores[2] = {"category": "hot", "confidence": 0.8, "reasoning": "wrong"}  # event 3 is warm
    report = run(scores=scores)
    event = report.events[2]
    assert (event.expected_category, event.got_category) == ("warm", "hot")
    assert not event.category_ok and not event.all_ok
    assert report.summary()["passed"]["category"] == 9
    assert report.summary()["all_passed"] == 9


def test_an_unmet_draft_point_fails_draft_relevance_and_is_recorded():
    point = TEST_SET[0]["draft_must_address"][2]  # "does not quote a price"
    report = run(judge=StubJudge(unmet=[point]))
    event = report.events[0]
    assert not event.draft_ok
    assert [p["point"] for p in event.judge if not p["met"]] == [point]
    assert report.summary()["passed"]["draft"] == 9


def test_a_dedup_miss_is_caught():
    # Same fakes, but the repo is told every lead is new: events 2, 9, 10 must fail dedup.
    from eval import runner

    class NoMergeRepo(InMemoryLeadRepository):
        def add_lead(self, inbound):
            self.records.clear()
            return super().add_lead(inbound)

    report = runner.run_eval(
        llm=FakeLLM(score=list(PERFECT_SCORES), draft=list(DRAFTS)),
        judge=StubJudge(),
        crm=FakeCrm(),
        repo=NoMergeRepo(),
    )
    failed = [e.id for e in report.events if not e.dedup_ok]
    assert failed == [2, 9, 10]


def test_a_crm_failure_is_graded_not_fatal():
    report = run(crm=FakeCrm(error=CrmError("HubSpot 401")))
    assert report.summary()["passed"]["crm"] == 0
    assert report.summary()["passed"]["category"] == 10
    assert "HubSpot 401" in (report.events[0].crm_error or "")


def test_a_scoring_failure_is_graded_not_fatal():
    scores = [dict(s) for s in PERFECT_SCORES]
    llm = FakeLLM(score=[LLMRefusal("no")] + scores[1:], draft=list(DRAFTS))
    report = run_eval(llm=llm, judge=StubJudge(), crm=FakeCrm(), repo=InMemoryLeadRepository())
    first = report.events[0]
    assert first.got_category is None and not first.category_ok
    assert not first.draft_ok and not first.crm_ok  # nothing was drafted or approved
    assert report.summary()["events"] == 10


def test_the_crm_state_hook_checks_what_the_crm_really_holds():
    seen = []

    def crm_state(external_id):
        seen.append(external_id)
        return {"lifecyclestage": "lead"}  # wrong for every non-cold event

    report = run(crm_state=crm_state)
    assert len(seen) == 10
    cold = [e for e in report.events if e.expected_category == "cold"]
    assert all(e.crm_ok for e in cold)
    assert not any(e.crm_ok for e in report.events if e.expected_category != "cold")


def test_latency_is_measured_per_event_and_summarised():
    ticks = iter(float(i) for i in range(1000))
    report = run(clock=lambda: next(ticks))
    event = report.events[0]
    assert event.webhook_s == 1.0 and event.approve_s == 1.0
    latency = report.summary()["latency_s"]
    assert set(latency) == {"webhook", "approve", "total"}
    assert latency["total"] == {"mean": 2.0, "p50": 2.0, "max": 2.0}


def test_markdown_reports_only_what_was_measured():
    report = run()
    text = to_markdown(report, models={"scorer": "fake-model", "judge": "stub-judge"})
    assert "fake-model" in text and "stub-judge" in text
    assert "10/10" in text
    assert text.count("| ") > 10  # a per-event table


def test_preflight_names_eval_leads_that_already_exist_in_the_crm():
    from eval.run import existing_contacts

    class Crm:
        def find_contact(self, contact):
            return "99" if contact["email"] == "mtorres88@yahoo.com" else None

    assert existing_contacts(Crm()) == ["#5 mike-torres (contact 99)"]
