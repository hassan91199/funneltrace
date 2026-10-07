import os
from dataclasses import dataclass

from dotenv import load_dotenv


def load_env(path: str | None = None) -> None:
    """Read backend/.env (if present) into the environment; real env vars win.

    Called by entrypoints, not by Settings.from_env, so tests never pick up a local .env."""
    load_dotenv(path)


@dataclass(frozen=True)
class Settings:
    database_url: str
    openai_api_key: str = ""
    hubspot_access_token: str = ""
    openai_model: str = "gpt-4o-mini"

    @classmethod
    def from_env(cls) -> "Settings":
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is required")
        return cls(
            database_url=database_url,
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            hubspot_access_token=os.environ.get("HUBSPOT_ACCESS_TOKEN", ""),
            openai_model=os.environ.get("OPENAI_MODEL") or "gpt-4o-mini",
        )
