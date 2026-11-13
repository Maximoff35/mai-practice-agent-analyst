"""Small FastAPI surface over the Analyst Agent."""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException
from pydantic import BaseModel, Field, field_validator

from analyst import (
    AnalysisResult,
    AnalystAgent,
    FakeLLMProvider,
    MAIConfigurationError,
    MAIError,
    MAIProvider,
    OpenRouterConfigurationError,
    OpenRouterError,
    OpenRouterProvider,
    SourceReferenceValidationError,
    UnsupportedRequirementsError,
)
from analyst.config import get_setting
from model_checker import case_result
from orchestration import CaseAcceptance, CaseAnalysis, CaseNotFoundError, CasePipeline, PipelineError, PipelineReport


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
    if provider_name == "mai":
        try:
            return AnalystAgent(MAIProvider.from_env())
        except MAIConfigurationError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error
    raise HTTPException(status_code=503, detail=f"Неизвестный LLM_PROVIDER: {provider_name}")


@lru_cache(maxsize=1)
def get_pipeline() -> CasePipeline:
    return CasePipeline(get_agent())


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/analyze", response_model=AnalysisResult)
def analyze(request: AnalyzeRequest, agent: Annotated[AnalystAgent, Depends(get_agent)]) -> AnalysisResult:
    try:
        return agent.analyze(request.requirements)
    except UnsupportedRequirementsError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except SourceReferenceValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (OpenRouterError, MAIError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/api/v2/analyze")
def analyze_case(request: AnalyzeRequest, agent: Annotated[AnalystAgent, Depends(get_agent)]) -> dict:
    result = analyze(request, agent)
    data = result.model_dump(mode="json")
    data["verification_result"] = case_result(result.verification_result, result.behavioral_model)
    data["counterexample"] = data["verification_result"]["counterexample"]
    for prop in data["behavioral_model"]["properties"]:
        prop["id"] = prop.pop("name")
    return data


@app.post("/api/v2/cases", response_model=CaseAnalysis)
def analyze_case_for_pipeline(
    request: AnalyzeRequest,
    pipeline: Annotated[CasePipeline, Depends(get_pipeline)],
) -> CaseAnalysis:
    try:
        return pipeline.analyze(request.requirements)
    except UnsupportedRequirementsError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except SourceReferenceValidationError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except (OpenRouterError, MAIError) as error:
        raise HTTPException(status_code=502, detail=str(error)) from error


@app.post("/api/v2/cases/{case_id}/accept", response_model=CaseAnalysis)
def accept_case(
    case_id: str,
    acceptance: CaseAcceptance,
    pipeline: Annotated[CasePipeline, Depends(get_pipeline)],
) -> CaseAnalysis:
    if acceptance.case_id != case_id:
        raise HTTPException(status_code=400, detail="case_id в пути и теле запроса должны совпадать")
    try:
        return pipeline.accept(acceptance)
    except CaseNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PipelineError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.post("/api/v2/cases/{case_id}/generate", response_model=PipelineReport)
def generate_case(
    case_id: str,
    pipeline: Annotated[CasePipeline, Depends(get_pipeline)],
) -> PipelineReport:
    try:
        return pipeline.generate(case_id)
    except CaseNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except PipelineError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error


@app.get("/api/v2/cases/{case_id}", response_model=PipelineReport)
def get_case_report(
    case_id: str,
    pipeline: Annotated[CasePipeline, Depends(get_pipeline)],
) -> PipelineReport:
    try:
        return pipeline.report(case_id)
    except CaseNotFoundError as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
