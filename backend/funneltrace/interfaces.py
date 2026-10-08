from dataclasses import dataclass
from typing import Protocol, runtime_checkable


class LLMRefusal(Exception):
    """The model declined to answer (structured-output refusal)."""


@runtime_checkable
class LeadLLM(Protocol):
    """The only way the app talks to an LLM, so tests can swap in a fake."""

    model: str

    def complete_json(self, system: str, user: str, schema: dict) -> dict: ...

    def complete_text(self, system: str, user: str) -> str: ...


class CrmError(Exception):
    """The CRM call failed or the adapter is not configured."""


@dataclass(frozen=True)
class CrmResult:
    external_id: str
    action: str  # create | update


@runtime_checkable
class CrmSync(Protocol):
    """The one internal CRM interface; HubSpot is the single real adapter."""

    name: str

    def upsert_contact(self, contact: dict) -> CrmResult:
        """Create or update the contact. `contact` has name, email, phone (digits),
        lifecycle_stage and, when the lead was synced before, external_id.
        Raises CrmError on failure."""
        ...
