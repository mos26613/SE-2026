from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from app import ai_gateway
from app.auth import CurrentUser, get_current_user
from app.config import Settings, get_settings

router = APIRouter(prefix="/api/ai", tags=["AI Gateway"])


class AIGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    system_instruction: Optional[str] = Field(default="You are a helpful assistant.", max_length=2000)


class AIGenerateResponse(BaseModel):
    response: str
    model: str


@router.post("/generate", response_model=AIGenerateResponse)
def generate_ai_content(
    payload: AIGenerateRequest,
    _user: CurrentUser = Depends(get_current_user),
    settings: Settings = Depends(get_settings),
) -> AIGenerateResponse:
    if not payload.prompt or not payload.prompt.strip():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Prompt must not be empty.",
        )

    if not settings.gemini_api_key:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="GEMINI_API_KEY is not configured.",
        )

    try:
        result = ai_gateway.generate_text(
            prompt=payload.prompt.strip(),
            system_instruction=(payload.system_instruction or "").strip(),
            settings=settings,
            response_mime_type="text/plain",
        )
        return AIGenerateResponse(response=result, model=settings.gemini_model)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Failed to generate AI response.",
        ) from exc