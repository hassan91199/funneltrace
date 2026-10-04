import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    database_url: str
    openai_api_key: str = ""
    hubspot_access_token: str = ""

    @classmethod
    def from_env(cls) -> "Settings":
        database_url = os.environ.get("DATABASE_URL")
        if not database_url:
            raise RuntimeError("DATABASE_URL is required")
        return cls(
            database_url=database_url,
            openai_api_key=os.environ.get("OPENAI_API_KEY", ""),
            hubspot_access_token=os.environ.get("HUBSPOT_ACCESS_TOKEN", ""),
        )
