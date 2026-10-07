from typing import Protocol, runtime_checkable


class LLMRefusal(Exception):
    """The model declined to answer (structured-output refusal)."""


@runtime_checkable
class LeadLLM(Protocol):
    """The only way the app talks to an LLM, so tests can swap in a fake."""

    model: str

    def complete_json(self, system: str, user: str, schema: dict) -> dict: ...

    def complete_text(self, system: str, user: str) -> str: ...


@runtime_checkable
class CrmSync(Protocol):
    """The one internal CRM interface; HubSpot is the single real adapter."""

    def upsert_contact(self, contact: dict) -> str:
        """Create or update the contact and return the CRM's id for it."""
        ...
