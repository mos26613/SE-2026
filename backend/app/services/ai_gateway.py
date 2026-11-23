import logging
import os
from typing import Any, Optional

import google.generativeai as genai

logger = logging.getLogger(__name__)


class AIGatewayError(Exception):
    """Custom exception for AI Gateway failures."""


class AIGatewayService:
    """
    Centralized AI Gateway service (US 5.1.1).
    All AI/Gemini calls in the backend must go through this single entry point.
    """

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
    ) -> None:
        self.api_key = api_key or os.getenv("GEMINI_API_KEY", "")
        self.model_name = model_name or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        self._model: Optional[Any] = None

        if self.api_key:
            genai.configure(api_key=self.api_key)
            self._model = genai.GenerativeModel(self.model_name)

    def generate_text(self, prompt: str, system_instruction: Optional[str] = None) -> str:
        """Send a controlled prompt to the AI model and return text response."""
        if not prompt or not prompt.strip():
            raise ValueError("Prompt must not be empty.")

        if not self.api_key or self._model is None:
            raise AIGatewayError("GEMINI_API_KEY is not configured in environment.")

        try:
            logger.info("Routing AI request through AIGatewayService (model=%s)", self.model_name)
            full_prompt = (
                f"{system_instruction.strip()}\n\n{prompt.strip()}"
                if system_instruction
                else prompt.strip()
            )
            response = self._model.generate_content(full_prompt)
            text = getattr(response, "text", None)
            if not text:
                raise AIGatewayError("Empty response received from AI provider.")
            return text.strip()
        except AIGatewayError:
            raise
        except Exception as exc:
            logger.error("AI Gateway provider error: %s", type(exc).__name__)
            raise AIGatewayError("Failed to generate AI response.") from exc


ai_gateway = AIGatewayService()
