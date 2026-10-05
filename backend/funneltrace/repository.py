import uuid
from dataclasses import dataclass
from typing import Protocol

import psycopg
from psycopg.types.json import Jsonb

from funneltrace.intake import InboundLead


@dataclass(frozen=True)
class StoredLead:
    lead_id: str
    message_id: str


class LeadRepository(Protocol):
    def add_lead(self, inbound: InboundLead) -> StoredLead: ...


class InMemoryLeadRepository:
    """Test double; also what the API tests run against."""

    def __init__(self) -> None:
        self.leads: list[InboundLead] = []

    def add_lead(self, inbound: InboundLead) -> StoredLead:
        self.leads.append(inbound)
        return StoredLead(lead_id=str(uuid.uuid4()), message_id=str(uuid.uuid4()))


class PgLeadRepository:
    def __init__(self, database_url: str) -> None:
        self._url = database_url

    def add_lead(self, inbound: InboundLead) -> StoredLead:
        with psycopg.connect(self._url) as conn:
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
            message_id = conn.execute(
                "INSERT INTO lead_messages (lead_id, channel, body, raw_payload) "
                "VALUES (%s, %s, %s, %s) RETURNING id",
                (lead_id, inbound.channel, inbound.message, Jsonb(inbound.raw_payload)),
            ).fetchone()[0]
        return StoredLead(lead_id=str(lead_id), message_id=str(message_id))
