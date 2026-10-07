from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, ConfigDict, Field

from funneltrace.config import Settings
from funneltrace.intake import InboundLead, normalize_web_form, normalize_whatsapp
from funneltrace.repository import LeadRepository, PgLeadRepository


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


def create_app(repo: LeadRepository | None = None) -> FastAPI:
    app = FastAPI(title="FunnelTrace")
    holder: dict = {"repo": repo}

    def get_repo() -> LeadRepository:
        # Built on first use so importing the app never needs a database.
        if holder["repo"] is None:
            holder["repo"] = PgLeadRepository(Settings.from_env().database_url)
        return holder["repo"]

    def store(inbound: InboundLead) -> dict:
        stored = get_repo().add_lead(inbound)
        return {
            "lead_id": stored.lead_id,
            "message_id": stored.message_id,
            "is_new": stored.is_new,
            "match_reason": stored.match_reason,
        }

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

    return app


app = create_app()
