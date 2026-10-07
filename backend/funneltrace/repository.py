import uuid
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol

import psycopg
from psycopg.types.json import Jsonb

from funneltrace.dedup import Candidate, find_match, merged_name
from funneltrace.intake import InboundLead
from funneltrace.scoring import ScoreResult


@dataclass(frozen=True)
class StoredLead:
    lead_id: str
    message_id: str
    is_new: bool
    match_reason: str | None = None


@dataclass(frozen=True)
class LeadContext:
    name: str
    messages: list[tuple[str, str]]  # (channel, body), oldest first
    email: str | None = None  # normalized, ready to use as a delivery address
    phone: str | None = None  # normalized digits


@dataclass(frozen=True)
class StoredScore:
    category: str
    confidence: float
    reasoning: str
    model: str


@dataclass(frozen=True)
class Draft:
    draft_id: str
    lead_id: str
    lead_name: str
    category: str | None
    reasoning: str | None
    subject: str
    body: str
    status: str  # pending | approved | rejected | superseded
    created_at: datetime
    decided_at: datetime | None = None


@dataclass(frozen=True)
class TraceEvent:
    type: str
    payload: dict


class LeadRepository(Protocol):
    def add_lead(self, inbound: InboundLead) -> StoredLead: ...

    def get_context(self, lead_id: str) -> LeadContext: ...

    def add_score(self, lead_id: str, score: ScoreResult, model: str) -> str: ...

    def scores_for(self, lead_id: str) -> list[StoredScore]: ...

    def add_draft(self, lead_id: str, scoring_id: str | None, subject: str, body: str) -> Draft:
        """Store a pending draft; any older pending draft of the lead becomes superseded."""
        ...

    def get_draft(self, draft_id: str) -> Draft | None: ...

    def list_drafts(self, status: str | None = None) -> list[Draft]:
        """Newest first."""
        ...

    def decide_draft(self, draft_id: str, status: str) -> Draft | None:
        """Move a pending draft to approved/rejected; None if it is not pending."""
        ...

    def log_event(self, lead_id: str, type: str, payload: dict) -> None: ...

    def events_for(self, lead_id: str) -> list[TraceEvent]: ...


@dataclass
class LeadRecord:
    lead_id: str
    name: str
    email: str | None
    phone: str | None
    normalized_email: str | None
    normalized_phone: str | None


class InMemoryLeadRepository:
    """Test double; also what the API tests run against.

    `leads` logs every inbound contact; `records` holds the deduped leads."""

    def __init__(self) -> None:
        self.leads: list[InboundLead] = []
        self.records: list[LeadRecord] = []
        self._messages: dict[str, list[tuple[str, str]]] = {}
        self._scores: dict[str, list[tuple[str, StoredScore]]] = {}
        self._drafts: list[tuple[Draft, str | None]] = []  # (draft, scoring_id)
        self._events: dict[str, list[TraceEvent]] = {}

    def add_lead(self, inbound: InboundLead) -> StoredLead:
        self.leads.append(inbound)
        match = find_match(
            inbound,
            [
                Candidate(r.lead_id, r.name, r.normalized_email, r.normalized_phone)
                for r in self.records
            ],
        )
        message_id = str(uuid.uuid4())
        if match is None:
            record = LeadRecord(
                str(uuid.uuid4()),
                inbound.name,
                inbound.email,
                inbound.phone,
                inbound.normalized_email,
                inbound.normalized_phone,
            )
            self.records.append(record)
            self._messages[record.lead_id] = [(inbound.channel, inbound.message)]
            return StoredLead(record.lead_id, message_id, is_new=True)
        record = next(r for r in self.records if r.lead_id == match.lead_id)
        self._messages[record.lead_id].append((inbound.channel, inbound.message))
        record.name = merged_name(record.name, inbound.name)
        if not record.normalized_email:
            record.email, record.normalized_email = inbound.email, inbound.normalized_email
        if not record.normalized_phone:
            record.phone, record.normalized_phone = inbound.phone, inbound.normalized_phone
        return StoredLead(record.lead_id, message_id, is_new=False, match_reason=match.reason)

    def get_context(self, lead_id: str) -> LeadContext:
        record = next(r for r in self.records if r.lead_id == lead_id)
        return LeadContext(
            record.name,
            list(self._messages[lead_id]),
            record.normalized_email,
            record.normalized_phone,
        )

    def add_score(self, lead_id: str, score: ScoreResult, model: str) -> str:
        scoring_id = str(uuid.uuid4())
        stored = StoredScore(score.category, score.confidence, score.reasoning, model)
        self._scores.setdefault(lead_id, []).append((scoring_id, stored))
        return scoring_id

    def scores_for(self, lead_id: str) -> list[StoredScore]:
        return [stored for _, stored in self._scores.get(lead_id, [])]

    def _replace(self, draft_id: str, **changes) -> Draft:
        for index, (draft, scoring_id) in enumerate(self._drafts):
            if draft.draft_id == draft_id:
                updated = replace(draft, **changes)
                self._drafts[index] = (updated, scoring_id)
                return updated
        raise KeyError(draft_id)

    def add_draft(self, lead_id: str, scoring_id: str | None, subject: str, body: str) -> Draft:
        for draft, _ in list(self._drafts):
            if draft.lead_id == lead_id and draft.status == "pending":
                self._replace(draft.draft_id, status="superseded")
        score = next((s for sid, s in self._scores.get(lead_id, []) if sid == scoring_id), None)
        draft = Draft(
            draft_id=str(uuid.uuid4()),
            lead_id=lead_id,
            lead_name=next(r.name for r in self.records if r.lead_id == lead_id),
            category=score.category if score else None,
            reasoning=score.reasoning if score else None,
            subject=subject,
            body=body,
            status="pending",
            created_at=datetime.now(UTC),
        )
        self._drafts.append((draft, scoring_id))
        return draft

    def get_draft(self, draft_id: str) -> Draft | None:
        return next((d for d, _ in self._drafts if d.draft_id == draft_id), None)

    def list_drafts(self, status: str | None = None) -> list[Draft]:
        drafts = [d for d, _ in self._drafts if status is None or d.status == status]
        return list(reversed(drafts))

    def decide_draft(self, draft_id: str, status: str) -> Draft | None:
        draft = self.get_draft(draft_id)
        if draft is None or draft.status != "pending":
            return None
        return self._replace(draft_id, status=status, decided_at=datetime.now(UTC))

    def log_event(self, lead_id: str, type: str, payload: dict) -> None:
        self._events.setdefault(lead_id, []).append(TraceEvent(type, payload))

    def events_for(self, lead_id: str) -> list[TraceEvent]:
        return list(self._events.get(lead_id, []))


class PgLeadRepository:
    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def add_lead(self, inbound: InboundLead) -> StoredLead:
        with psycopg.connect(self._url) as conn:
            rows = conn.execute(
                "SELECT id, name, normalized_email, normalized_phone FROM leads "
                "WHERE (normalized_email IS NOT NULL AND normalized_email = %s) "
                "OR (normalized_phone IS NOT NULL AND normalized_phone = %s) "
                "ORDER BY created_at",
                (inbound.normalized_email, inbound.normalized_phone),
            ).fetchall()
            match = find_match(inbound, [Candidate(str(r[0]), *r[1:]) for r in rows])
            if match is None:
                lead_id = conn.execute(
                    "INSERT INTO leads (name, email, phone, normalized_email, normalized_phone) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                    (
                        inbound.name,
                        inbound.email,
                        inbound.phone,
                        inbound.normalized_email,
                        inbound.normalized_phone,
                    ),
                ).fetchone()[0]
            else:
                lead_id = match.lead_id
                current = next(r[1] for r in rows if str(r[0]) == lead_id)
                conn.execute(
                    "UPDATE leads SET name = %s, "
                    "email = COALESCE(email, %s), "
                    "normalized_email = COALESCE(normalized_email, %s), "
                    "phone = COALESCE(phone, %s), "
                    "normalized_phone = COALESCE(normalized_phone, %s), "
                    "updated_at = now() WHERE id = %s",
                    (
                        merged_name(current, inbound.name),
                        inbound.email,
                        inbound.normalized_email,
                        inbound.phone,
                        inbound.normalized_phone,
                        lead_id,
                    ),
                )
            message_id = conn.execute(
                "INSERT INTO lead_messages (lead_id, channel, body, raw_payload, match_reason) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (
                    lead_id,
                    inbound.channel,
                    inbound.message,
                    Jsonb(inbound.raw_payload),
                    match.reason if match else None,
                ),
            ).fetchone()[0]
        return StoredLead(
            lead_id=str(lead_id),
            message_id=str(message_id),
            is_new=match is None,
            match_reason=match.reason if match else None,
        )

    def get_context(self, lead_id: str) -> LeadContext:
        with psycopg.connect(self._url) as conn:
            name, email, phone = conn.execute(
                "SELECT name, normalized_email, normalized_phone FROM leads WHERE id = %s",
                (lead_id,),
            ).fetchone()
            rows = conn.execute(
                "SELECT channel, body FROM lead_messages WHERE lead_id = %s "
                "ORDER BY received_at, id",
                (lead_id,),
            ).fetchall()
        return LeadContext(name, [(channel, body) for channel, body in rows], email, phone)

    def add_score(self, lead_id: str, score: ScoreResult, model: str) -> str:
        with psycopg.connect(self._url) as conn:
            scoring_id = conn.execute(
                "INSERT INTO scoring_history (lead_id, category, confidence, reasoning, model) "
                "VALUES (%s, %s, %s, %s, %s) RETURNING id",
                (lead_id, score.category, score.confidence, score.reasoning, model),
            ).fetchone()[0]
        return str(scoring_id)

    def scores_for(self, lead_id: str) -> list[StoredScore]:
        with psycopg.connect(self._url) as conn:
            rows = conn.execute(
                "SELECT category, confidence, reasoning, model FROM scoring_history "
                "WHERE lead_id = %s ORDER BY created_at, id",
                (lead_id,),
            ).fetchall()
        return [StoredScore(*row) for row in rows]

    _DRAFT_SELECT = (
        "SELECT d.id, d.lead_id, l.name, s.category, s.reasoning, d.subject, d.body, "
        "d.status, d.created_at, d.decided_at "
        "FROM drafts d JOIN leads l ON l.id = d.lead_id "
        "LEFT JOIN scoring_history s ON s.id = d.scoring_id "
    )

    @staticmethod
    def _draft(row) -> Draft:
        return Draft(str(row[0]), str(row[1]), *row[2:])

    def add_draft(self, lead_id: str, scoring_id: str | None, subject: str, body: str) -> Draft:
        with psycopg.connect(self._url) as conn:
            conn.execute(
                "UPDATE drafts SET status = 'superseded' WHERE lead_id = %s AND status = 'pending'",
                (lead_id,),
            )
            draft_id = conn.execute(
                "INSERT INTO drafts (lead_id, scoring_id, subject, body) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (lead_id, scoring_id, subject, body),
            ).fetchone()[0]
            row = conn.execute(self._DRAFT_SELECT + "WHERE d.id = %s", (draft_id,)).fetchone()
        return self._draft(row)

    def get_draft(self, draft_id: str) -> Draft | None:
        with psycopg.connect(self._url) as conn:
            row = conn.execute(self._DRAFT_SELECT + "WHERE d.id = %s", (draft_id,)).fetchone()
        return self._draft(row) if row else None

    def list_drafts(self, status: str | None = None) -> list[Draft]:
        with psycopg.connect(self._url) as conn:
            rows = conn.execute(
                self._DRAFT_SELECT + "WHERE (%s::text IS NULL OR d.status = %s) "
                "ORDER BY d.created_at DESC, d.id",
                (status, status),
            ).fetchall()
        return [self._draft(row) for row in rows]

    def decide_draft(self, draft_id: str, status: str) -> Draft | None:
        with psycopg.connect(self._url) as conn:
            updated = conn.execute(
                "UPDATE drafts SET status = %s, decided_at = now() "
                "WHERE id = %s AND status = 'pending' RETURNING id",
                (status, draft_id),
            ).fetchone()
            if updated is None:
                return None
            row = conn.execute(self._DRAFT_SELECT + "WHERE d.id = %s", (draft_id,)).fetchone()
        return self._draft(row)

    def log_event(self, lead_id: str, type: str, payload: dict) -> None:
        with psycopg.connect(self._url) as conn:
            conn.execute(
                "INSERT INTO trace_events (lead_id, type, payload) VALUES (%s, %s, %s)",
                (lead_id, type, Jsonb(payload)),
            )

    def events_for(self, lead_id: str) -> list[TraceEvent]:
        with psycopg.connect(self._url) as conn:
            rows = conn.execute(
                "SELECT type, payload FROM trace_events WHERE lead_id = %s ORDER BY id",
                (lead_id,),
            ).fetchall()
        return [TraceEvent(*row) for row in rows]
