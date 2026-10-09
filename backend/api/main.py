"""Small FastAPI surface over the Analyst Agent."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from analyst import (
    AnalysisResult,
    AnalystAgent,
    FakeLLMProvider,
    OpenRouterConfigurationError,
    OpenRouterError,
    OpenRouterProvider,
    UnsupportedRequirementsError,
)
from analyst.config import get_setting


app = FastAPI(title="MAI Analyst Agent")


class AnalyzeRequest(BaseModel):
    requirements: str = Field(min_length=1)

    @field_validator("requirements")
    @classmethod
    def require_nonblank_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("requirements не должен быть пустым")
        return value


def get_agent() -> AnalystAgent:
    provider_name = (get_setting("LLM_PROVIDER", "fake") or "fake").casefold()
    if provider_name == "fake":
        return AnalystAgent(FakeLLMProvider())
    if provider_name == "openrouter":
        try:
            return AnalystAgent(OpenRouterProvider.from_env())
        except OpenRouterConfigurationError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
    raise HTTPException(status_code=503, detail=f"Неизвестный LLM_PROVIDER: {provider_name}")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalysisResult)
def analyze(request: AnalyzeRequest, agent: Annotated[AnalystAgent, Depends(get_agent)]) -> AnalysisResult:
    try:
        return agent.analyze(request.requirements)
    except UnsupportedRequirementsError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except OpenRouterError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
