"""MAI LiteLLM provider, following https://api-ai.mai.ru/openapi.json."""

from __future__ import annotations

import json
import math
import ssl

import httpx

from model_checker import BehavioralModel, VerificationResult, validate_model, validate_source_references

from .config import get_setting
from .prompts import EXPLANATION_INSTRUCTIONS, MODEL_INSTRUCTIONS


class MAIError(RuntimeError):
    """A sanitized provider error, safe to return from the API."""


class MAIConfigurationError(MAIError):
    pass


class MAIAPIError(MAIError):
    pass


class MAIResponseError(MAIError):
    pass


class MAIProvider:
    def __init__(
        self,
        api_key: str,
        model: str,
        *,
        base_url: str = "https://api-ai.mai.ru",
        timeout_seconds: float = 90.0,
        client: httpx.Client | None = None,
    ) -> None:
        if not api_key.strip():
            raise MAIConfigurationError("MAI_API_KEY не задан")
        if not model.strip():
            raise MAIConfigurationError("MAI_MODEL не задан")
        try:
            url = httpx.URL(base_url)
        except httpx.InvalidURL as error:
            raise MAIConfigurationError("MAI_BASE_URL содержит некорректный адрес") from error
        if url.scheme != "https" or not url.host or url.username or url.password or url.query or url.fragment:
            raise MAIConfigurationError("MAI_BASE_URL должен быть HTTPS-адресом без учётных данных и параметров")
        if not math.isfinite(timeout_seconds) or timeout_seconds <= 0:
            raise MAIConfigurationError("MAI_TIMEOUT_SECONDS должен быть конечным положительным числом")
        self._api_key = api_key.strip()
        self.model = model.strip()
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._client = client
        self.response_models: list[str] = []

    @classmethod
    def from_env(cls, *, client: httpx.Client | None = None) -> "MAIProvider":
        try:
            timeout = float(get_setting("MAI_TIMEOUT_SECONDS", "90") or "90")
        except ValueError as error:
            raise MAIConfigurationError("MAI_TIMEOUT_SECONDS должен быть числом") from error
        return cls(
            api_key=get_setting("MAI_API_KEY") or "",
            model=get_setting("MAI_MODEL") or "",
            base_url=get_setting("MAI_BASE_URL") or "https://api-ai.mai.ru",
            timeout_seconds=timeout,
            client=client,
        )

    def _request(self, messages: list[dict[str, str]], *, structured: bool) -> str:
        payload = {"model": self.model, "messages": messages, "stream": False, "temperature": 0, "max_tokens": 8192}
        if structured:
            payload["response_format"] = {"type": "json_object"}
        headers = {"x-litellm-api-key": self._api_key, "Content-Type": "application/json"}
        try:
            if self._client is None:
                # Use system trust roots, including the Windows certificate store.
                with httpx.Client(timeout=self.timeout_seconds, verify=ssl.create_default_context()) as client:
                    response = client.post(f"{self.base_url}/v1/chat/completions", headers=headers, json=payload)
            else:
                response = self._client.post(
                    f"{self.base_url}/v1/chat/completions", headers=headers, json=payload,
                    timeout=self.timeout_seconds,
                )
        except httpx.RequestError as error:
            raise MAIAPIError(f"Не удалось обратиться к API МАИ: {type(error).__name__}") from error
        if response.status_code != 200:
            raise MAIAPIError(f"API МАИ вернул HTTP {response.status_code}")
        try:
            data = response.json()
            if "error" in data:
                raise MAIAPIError("API МАИ сообщил об ошибке провайдера")
            choice = data["choices"][0]
            content = choice["message"]["content"]
            if choice.get("finish_reason") != "stop":
                raise MAIResponseError("API МАИ вернул незавершённый ответ")
            if not isinstance(content, str) or not content.strip():
                raise MAIResponseError("API МАИ вернул пустой или нетекстовый ответ")
        except (ValueError, KeyError, IndexError, TypeError) as error:
            raise MAIResponseError("Некорректная структура ответа API МАИ") from error
        actual_model = data.get("model")
        if isinstance(actual_model, str) and actual_model:
            self.response_models.append(actual_model)
        return content.strip()

    def build_model(self, requirements: str) -> BehavioralModel:
        content = self._request(
            [{"role": "system", "content": MODEL_INSTRUCTIONS}, {"role": "user", "content": requirements}],
            structured=True,
        )
        try:
            return validate_source_references(validate_model(json.loads(content)), requirements)
        except (ValueError, TypeError) as error:
            # Validation details include untrusted model values; keep them out of HTTP errors.
            raise MAIResponseError("API МАИ вернул невалидную BehavioralModel или JSON") from error

    def explain_result(self, requirements: str, model: BehavioralModel, result: VerificationResult) -> str:
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
        )
