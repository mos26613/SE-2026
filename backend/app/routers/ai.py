from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel, Field

from app.services.ai_gateway import AIGatewayError, ai_gateway

router = APIRouter(prefix="/api/ai", tags=["AI Gateway"])


class AIGenerateRequest(BaseModel):
    prompt: str = Field(..., min_length=1, max_length=8000)
    system_instruction: Optional[str] = Field(default=None, max_length=2000)


class AIGenerateResponse(BaseModel):
    response: str
    model: str


@router.post("/generate", response_model=AIGenerateResponse)
def generate_ai_content(payload: AIGenerateRequest) -> AIGenerateResponse:
    try:
        result = ai_gateway.generate_text(
            prompt=payload.prompt,
            system_instruction=payload.system_instruction,
        )
        return AIGenerateResponse(response=result, model=ai_gateway.model_name)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except AIGatewayError as exc:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=str(exc),
        ) from exc
