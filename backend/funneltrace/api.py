import logging
import uuid
from typing import Literal

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from funneltrace.config import Settings, load_env
from funneltrace.drafting import DraftingError, draft_followup
from funneltrace.intake import InboundLead, normalize_web_form, normalize_whatsapp
from funneltrace.interfaces import LeadLLM
from funneltrace.openai_llm import OpenAILLM
from funneltrace.repository import Draft, LeadRepository, PgLeadRepository
from funneltrace.scoring import ScoringError, score_lead

logger = logging.getLogger("funneltrace.outbound")

DraftStatus = Literal["pending", "approved", "rejected", "superseded"]


def draft_json(draft: Draft) -> dict:
    return {
        "id": draft.draft_id,
        "lead_id": draft.lead_id,
        "lead_name": draft.lead_name,
        "category": draft.category,
        "reasoning": draft.reasoning,
        "subject": draft.subject,
        "body": draft.body,
        "status": draft.status,
        "created_at": draft.created_at.isoformat(),
        "decided_at": draft.decided_at.isoformat() if draft.decided_at else None,
    }


class WebFormPayload(BaseModel):
    name: str
    email: str = ""
    phone: str = ""
    message: str


class WhatsAppPayload(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    profile_name: str = ""
    text: str


def create_app(repo: LeadRepository | None = None, llm: LeadLLM | None = None) -> FastAPI:
    app = FastAPI(title="FunnelTrace")
    holder: dict = {"repo": repo, "llm": llm}

    def get_repo() -> LeadRepository:
        # Built on first use so importing the app never needs a database.
        if holder["repo"] is None:
            load_env()
            holder["repo"] = PgLeadRepository(Settings.from_env().database_url)
        return holder["repo"]

    def get_llm() -> LeadLLM:
        if holder["llm"] is None:
            load_env()
            settings = Settings.from_env()
            holder["llm"] = OpenAILLM(settings.openai_api_key, settings.openai_model)
        return holder["llm"]

    def triage(lead_id: str) -> dict:
        """Score the lead, then draft a reply held for approval. A failure in either step
        must not lose the lead (already stored), so errors are reported, not raised."""
        repo = get_repo()
        try:
            llm = get_llm()
            context = repo.get_context(lead_id)
            result = score_lead(llm, context.name, context.messages)
        except ScoringError as exc:
            return {"score": None, "score_error": str(exc), "draft": None}
        scoring_id = repo.add_score(lead_id, result, llm.model)
        out: dict = {
            "score": {
                "category": result.category,
                "confidence": result.confidence,
                "reasoning": result.reasoning,
            }
        }
        try:
            content = draft_followup(llm, context.name, result, context.messages)
        except DraftingError as exc:
            return {**out, "draft": None, "draft_error": str(exc)}
        draft = repo.add_draft(lead_id, scoring_id, content.subject, content.body)
        return {**out, "draft": draft_json(draft)}

    def store(inbound: InboundLead) -> dict:
        stored = get_repo().add_lead(inbound)
        return {
            "lead_id": stored.lead_id,
            "message_id": stored.message_id,
            "is_new": stored.is_new,
            "match_reason": stored.match_reason,
            **triage(stored.lead_id),
        }

    def would_send_payload(draft: Draft) -> dict:
        context = get_repo().get_context(draft.lead_id)
        channel = context.messages[-1][0]
        # Reply where the lead last wrote: email for the form, phone for WhatsApp.
        if channel == "web_form" and context.email:
            to = context.email
        else:
            to = context.phone or context.email
        return {
            "draft_id": draft.draft_id,
            "channel": channel,
            "to": to,
            "subject": draft.subject,
            "body": draft.body,
        }

    def decide(draft_id: str, status: str) -> dict:
        repo = get_repo()
        try:
            uuid.UUID(draft_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="draft not found") from None
        if repo.get_draft(draft_id) is None:
            raise HTTPException(status_code=404, detail="draft not found")
        draft = repo.decide_draft(draft_id, status)
        if draft is None:
            raise HTTPException(status_code=409, detail="draft is already decided")
        out: dict = {"draft": draft_json(draft)}
        if status == "approved":
            # Nothing leaves the system: the "send" is a logged payload, only after approval.
            payload = would_send_payload(draft)
            repo.log_event(draft.lead_id, "would_send", payload)
            logger.info("would send: %s", payload)
            out["would_send"] = payload
        return out

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok"}

    @app.post("/webhooks/web-form", status_code=201)
    def web_form(payload: WebFormPayload) -> dict:
        try:
            inbound = normalize_web_form(payload.model_dump())
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return store(inbound)

    @app.post("/webhooks/whatsapp", status_code=201)
    def whatsapp(payload: WhatsAppPayload) -> dict:
        try:
            inbound = normalize_whatsapp(payload.model_dump(by_alias=True))
        except ValueError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return store(inbound)

    @app.get("/drafts")
    def list_drafts(status: DraftStatus | None = None) -> list[dict]:
        return [draft_json(d) for d in get_repo().list_drafts(status)]

    @app.get("/drafts/{draft_id}")
    def get_draft(draft_id: str) -> dict:
        try:
            uuid.UUID(draft_id)
        except ValueError:
            raise HTTPException(status_code=404, detail="draft not found") from None
        draft = get_repo().get_draft(draft_id)
        if draft is None:
            raise HTTPException(status_code=404, detail="draft not found")
        return draft_json(draft)

    @app.post("/drafts/{draft_id}/approve")
    def approve(draft_id: str) -> dict:
        return decide(draft_id, "approved")

    @app.post("/drafts/{draft_id}/reject")
    def reject(draft_id: str) -> dict:
        return decide(draft_id, "rejected")

    return app


app = create_app()
