import os

import pytest

from funneltrace.config import Settings


def test_settings_read_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5433/db")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    monkeypatch.setenv("HUBSPOT_ACCESS_TOKEN", "hs-test")
    s = Settings.from_env()
    assert s.database_url == "postgresql://u:p@localhost:5433/db"
    assert s.openai_api_key == "sk-test"
    assert s.hubspot_access_token == "hs-test"


def test_optional_keys_default_to_empty(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5433/db")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("HUBSPOT_ACCESS_TOKEN", raising=False)
    s = Settings.from_env()
    assert s.openai_api_key == ""
    assert s.hubspot_access_token == ""
    assert s.openai_model == "gpt-4o-mini"


def test_openai_model_can_be_overridden(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@localhost:5433/db")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-test")
    assert Settings.from_env().openai_model == "gpt-test"


def test_database_url_is_required(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    with pytest.raises(RuntimeError, match="DATABASE_URL"):
        Settings.from_env()


def test_load_env_reads_a_dotenv_file_but_real_env_vars_win(tmp_path, monkeypatch):
    from funneltrace.config import load_env

    env_file = tmp_path / ".env"
    env_file.write_text("OPENAI_API_KEY=from-file\nOPENAI_MODEL=model-from-file\n")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.setenv("OPENAI_MODEL", "model-from-shell")
    load_env(str(env_file))
    assert os.environ["OPENAI_API_KEY"] == "from-file"
    assert os.environ["OPENAI_MODEL"] == "model-from-shell"
    monkeypatch.delenv("OPENAI_API_KEY")


def test_replies_are_written_by_gpt_5_4_mini_unless_set_separately(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://x")
    monkeypatch.setenv("OPENAI_MODEL", "gpt-main")
    monkeypatch.delenv("OPENAI_DRAFT_MODEL", raising=False)
    s = Settings.from_env()
    assert (s.openai_model, s.openai_draft_model) == ("gpt-main", "gpt-5.4-mini")
    monkeypatch.setenv("OPENAI_DRAFT_MODEL", "gpt-writer")
    assert Settings.from_env().openai_draft_model == "gpt-writer"
