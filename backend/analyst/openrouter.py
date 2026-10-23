"""OpenRouter implementation of the Analyst Agent provider contract."""

from __future__ import annotations

import json
from typing import Any

import httpx
from pydantic import ValidationError

from model_checker import (
    BehavioralModel,
    ModelValidationError,
    SourceReferenceValidationError,
    VerificationResult,
    validate_model,
    validate_source_references,
)

from .config import get_setting
from .prompts import EXPLANATION_INSTRUCTIONS, MODEL_INSTRUCTIONS


OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"


class OpenRouterError(RuntimeError):
    """Base error for configuration, transport and response failures."""


class OpenRouterConfigurationError(OpenRouterError):
    pass


class OpenRouterAPIError(OpenRouterError):
    pass


class OpenRouterResponseError(OpenRouterError):
    pass


class OpenRouterModelError(OpenRouterResponseError):
    pass


class OpenRouterProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        client: httpx.Client | None = None,
        timeout_seconds: float = 90.0,
    ) -> None:
        if not api_key.strip():
            raise OpenRouterConfigurationError("OPENROUTER_API_KEY не задан")
        if not model.strip():
            raise OpenRouterConfigurationError("OPENROUTER_MODEL не задан")
        self._api_key = api_key
        self.model = model
        self._client = client
        self.timeout_seconds = timeout_seconds
        self.response_models: list[str] = []

    @classmethod
    def from_env(cls, *, client: httpx.Client | None = None) -> "OpenRouterProvider":
        return cls(
            api_key=get_setting("OPENROUTER_API_KEY") or "",
            model=get_setting("OPENROUTER_MODEL") or "",
            client=client,
        )

    def _request(self, messages: list[dict[str, str]], *, structured: bool) -> str:
        payload: dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "stream": False,
        }
        if structured:
            payload["response_format"] = {"type": "json_object"}
            payload["provider"] = {"require_parameters": True}
        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }
        try:
            if self._client is None:
                with httpx.Client(timeout=self.timeout_seconds) as client:
                    response = client.post(OPENROUTER_URL, headers=headers, json=payload)
            else:
                response = self._client.post(OPENROUTER_URL, headers=headers, json=payload)
        except httpx.RequestError as error:
            raise OpenRouterAPIError(f"Не удалось обратиться к OpenRouter: {type(error).__name__}") from error
        if response.status_code >= 400:
            raise OpenRouterAPIError(f"OpenRouter API вернул HTTP {response.status_code}")
        try:
            data = response.json()
            if isinstance(data, dict) and "error" in data:
                detail = data["error"]
                if isinstance(detail, dict):
                    detail = detail.get("message", "ошибка без описания")
                detail = str(detail).replace(self._api_key, "[скрыто]")[:500]
                raise OpenRouterAPIError(f"OpenRouter вернул ошибку: {detail}")
            choice = data["choices"][0]
            content = choice["message"]["content"]
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise OpenRouterResponseError("Некорректная структура ответа OpenRouter") from error
        if choice.get("finish_reason") == "length":
            raise OpenRouterResponseError("Ответ OpenRouter оборван из-за ограничения длины")
        if not isinstance(content, str) or not content.strip():
            raise OpenRouterResponseError("OpenRouter вернул пустой или нетекстовый ответ")
        actual_model = data.get("model")
        if isinstance(actual_model, str) and actual_model:
            self.response_models.append(actual_model)
        return content

    def build_model(self, requirements: str) -> BehavioralModel:
        content = self._request(
            [
                {"role": "system", "content": MODEL_INSTRUCTIONS},
                {"role": "user", "content": requirements},
            ],
            structured=True,
        )
        try:
            data = json.loads(content)
        except json.JSONDecodeError as error:
            raise OpenRouterResponseError("OpenRouter вернул невалидный JSON модели") from error
        try:
            model = validate_model(data)
            return validate_source_references(model, requirements)
        except (ValidationError, ModelValidationError, SourceReferenceValidationError, ValueError, TypeError) as error:
            raise OpenRouterModelError(f"OpenRouter вернул невалидную BehavioralModel: {error}") from error

    def explain_result(
        self,
        requirements: str,
        model: BehavioralModel,
        result: VerificationResult,
    ) -> str:
        context = {
            "requirements": requirements,
            "behavioral_model": model.model_dump(mode="json"),
            "verification_result": result.model_dump(mode="json", exclude={"stdout", "stderr"}),
            "counterexample": [state.model_dump(mode="json") for state in result.counterexample],
        }
        return self._request(
            [
                {"role": "system", "content": EXPLANATION_INSTRUCTIONS},
                {"role": "user", "content": json.dumps(context, ensure_ascii=False)},
            ],
            structured=False,
        ).strip()
