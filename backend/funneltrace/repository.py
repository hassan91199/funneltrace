import uuid
from dataclasses import dataclass
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


@dataclass(frozen=True)
class StoredScore:
    category: str
    confidence: float
    reasoning: str
    model: str


class LeadRepository(Protocol):
    def add_lead(self, inbound: InboundLead) -> StoredLead: ...

    def get_context(self, lead_id: str) -> LeadContext: ...

    def add_score(self, lead_id: str, score: ScoreResult, model: str) -> None: ...

    def scores_for(self, lead_id: str) -> list[StoredScore]: ...


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
        self._scores: dict[str, list[StoredScore]] = {}

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
        return LeadContext(record.name, list(self._messages[lead_id]))

    def add_score(self, lead_id: str, score: ScoreResult, model: str) -> None:
        self._scores.setdefault(lead_id, []).append(
            StoredScore(score.category, score.confidence, score.reasoning, model)
        )

    def scores_for(self, lead_id: str) -> list[StoredScore]:
        return list(self._scores.get(lead_id, []))


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
            name = conn.execute("SELECT name FROM leads WHERE id = %s", (lead_id,)).fetchone()[0]
            rows = conn.execute(
                "SELECT channel, body FROM lead_messages WHERE lead_id = %s "
                "ORDER BY received_at, id",
                (lead_id,),
            ).fetchall()
        return LeadContext(name, [(channel, body) for channel, body in rows])

    def add_score(self, lead_id: str, score: ScoreResult, model: str) -> None:
        with psycopg.connect(self._url) as conn:
            conn.execute(
                "INSERT INTO scoring_history (lead_id, category, confidence, reasoning, model) "
                "VALUES (%s, %s, %s, %s, %s)",
                (lead_id, score.category, score.confidence, score.reasoning, model),
            )

    def scores_for(self, lead_id: str) -> list[StoredScore]:
        with psycopg.connect(self._url) as conn:
            rows = conn.execute(
                "SELECT category, confidence, reasoning, model FROM scoring_history "
                "WHERE lead_id = %s ORDER BY created_at, id",
                (lead_id,),
            ).fetchall()
        return [StoredScore(*row) for row in rows]
