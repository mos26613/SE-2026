from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app import ai_gateway
from app.config import Settings


def _test_settings(**overrides) -> Settings:
    values = {
        "supabase_url": "",
        "gemini_api_key": "test-key",
        "gemini_model": "gemini-3.5-flash-lite",
        "gemini_timeout_seconds": 60.0,
        "gemini_thinking_level": "minimal",
    }
    values.update(overrides)
    return Settings(_env_file=None, **values)


def test_gateway_generates_text_successfully(monkeypatch):
    mock_models = MagicMock()
    mock_models.generate_content.return_value = MagicMock(text="  Hello student!  ")
    mock_client = MagicMock(models=mock_models)

    import google.genai

    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: mock_client)

    result = ai_gateway.generate_text(
        prompt="Summarize my tasks",
        system_instruction="Be concise",
        settings=_test_settings(),
    )
    assert result == "  Hello student!  "
    mock_models.generate_content.assert_called_once()


def test_gateway_returns_empty_when_api_key_missing():
    result = ai_gateway.generate_text(
        prompt="Hello",
        system_instruction="Be concise",
        settings=_test_settings(gemini_api_key=""),
    )
    assert result == ""


def test_gateway_retries_transient_error_once(monkeypatch):
    calls = []
    outcomes = [RuntimeError("503 UNAVAILABLE"), MagicMock(text="recovered")]

    class FakeModels:
        @staticmethod
        def generate_content(**kwargs):
            calls.append(1)
            item = outcomes.pop(0)
            if isinstance(item, Exception):
                raise item
            return item

    import google.genai

    monkeypatch.setattr(google.genai, "Client", lambda **kwargs: MagicMock(models=FakeModels()))
    monkeypatch.setattr(ai_gateway, "RETRY_DELAY_SECONDS", 0)

    result = ai_gateway.generate_text(
        prompt="Hello",
        system_instruction="Be concise",
        settings=_test_settings(),
    )
    assert result == "recovered"
    assert len(calls) == 2


def test_no_direct_gemini_imports_outside_gateway():
    app_dir = Path(__file__).resolve().parents[1] / "app"
    for py_file in app_dir.rglob("*.py"):
        if py_file.name == "ai_gateway.py":
            continue
        content = py_file.read_text(encoding="utf-8")
        assert "from google import genai" not in content, f"Direct genai import in {py_file}"
        assert "google.generativeai" not in content, f"Legacy generativeai import in {py_file}"