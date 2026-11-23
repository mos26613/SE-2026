from pathlib import Path
from unittest.mock import MagicMock

import pytest

from app.services.ai_gateway import AIGatewayError, AIGatewayService


def test_gateway_generates_text_successfully():
    service = AIGatewayService(api_key="test-key", model_name="gemini-2.5-flash")
    mock_model = MagicMock()
    mock_model.generate_content.return_value = MagicMock(text="  Hello student!  ")
    service._model = mock_model

    result = service.generate_text("Summarize my tasks")
    assert result == "Hello student!"
    mock_model.generate_content.assert_called_once_with("Summarize my tasks")


def test_gateway_rejects_empty_prompt():
    service = AIGatewayService(api_key="test-key")
    with pytest.raises(ValueError):
        service.generate_text("   ")


def test_gateway_raises_when_api_key_missing(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    service = AIGatewayService(api_key="")
    with pytest.raises(AIGatewayError):
        service.generate_text("Hello")


def test_no_direct_gemini_imports_outside_gateway():
    app_dir = Path(__file__).resolve().parents[1] / "app"
    for py_file in app_dir.rglob("*.py"):
        if py_file.name == "ai_gateway.py":
            continue
        content = py_file.read_text(encoding="utf-8")
        assert "google.generativeai" not in content, (
            f"Direct Gemini import found outside AI Gateway in {py_file}"
        )
