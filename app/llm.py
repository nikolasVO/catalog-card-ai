"""OpenAI-compatible and native Ollama APIs with safe transport/shape errors."""
import asyncio
import json
from typing import Any

import httpx

from app.config import Settings
from app.errors import ServiceError
from app.prompts import RESPONSE_SCHEMA, SYSTEM_PROMPT, user_prompt
from app.schemas import ProductInput


def _reject_json_constant(_value: str) -> None:
    raise ValueError("Non-finite numbers are not valid JSON")


class LLMClient:
    def __init__(self, settings: Settings, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    async def generate(self, product: ProductInput, correction: str = "") -> dict[str, Any]:
        is_ollama = self.settings.provider == "ollama"
        if not is_ollama and (not self.settings.api_key or self.settings.api_key == "replace-with-your-api-key"):
            raise ServiceError(
                "API_KEY_MISSING",
                "Не задан OPENAI_API_KEY. Создайте .env по образцу .env.example.",
                503,
            )
        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt(product, correction)},
        ]
        if is_ollama:
            endpoint = f"{self.settings.ollama_base_url.rstrip('/')}/api/chat"
            payload = {
                "model": self.settings.ollama_model,
                "messages": messages,
                "stream": False,
                "think": False,
                "format": RESPONSE_SCHEMA["json_schema"]["schema"],
                "options": {"temperature": 0, "num_predict": 2500, "num_ctx": 8192},
            }
            headers = {}
        else:
            endpoint = f"{self.settings.base_url.rstrip('/')}/chat/completions"
            payload = {
                "model": self.settings.model,
                "messages": messages,
                "response_format": RESPONSE_SCHEMA,
                "max_completion_tokens": 2500,
            }
            headers = {"Authorization": f"Bearer {self.settings.api_key}"}
        timeout = httpx.Timeout(self.settings.timeout_seconds)
        try:
            async with httpx.AsyncClient(
                timeout=timeout, transport=self.transport, follow_redirects=False
            ) as client:
                for attempt in range(3):
                    try:
                        response = await client.post(
                            endpoint,
                            headers=headers, json=payload,
                        )
                    except httpx.TimeoutException as exc:
                        if attempt < 2:
                            await asyncio.sleep(0.3 * (2 ** attempt))
                            continue
                        raise ServiceError("LLM_TIMEOUT", "LLM API не ответил вовремя.", 504) from exc
                    except httpx.InvalidURL as exc:
                        raise ServiceError("CONFIG_INVALID", "Некорректный адрес LLM API в настройках.", 503) from exc
                    except httpx.RequestError as exc:
                        raise ServiceError("LLM_NETWORK", "Не удалось связаться с LLM API.", 503) from exc

                    if response.status_code in {429, 500, 502, 503, 504} and attempt < 2:
                        await asyncio.sleep(0.3 * (2 ** attempt))
                        continue
                    break
        except ServiceError:
            raise

        if response.status_code in {401, 403}:
            message = (
                "LLM API отклонил доступ. Проверьте адрес и настройки сервера Ollama."
                if is_ollama else "Ошибка авторизации в LLM API. Проверьте API-ключ."
            )
            raise ServiceError("LLM_AUTH", message, 502)
        if response.status_code == 429:
            raise ServiceError("LLM_RATE_LIMIT", "Превышен лимит запросов LLM API.", 503)
        if not response.is_success:
            raise ServiceError(
                "LLM_HTTP_ERROR",
                f"LLM API вернул HTTP {response.status_code}. Проверьте модель и формат API.",
                502,
            )
        try:
            data = response.json()
            if not isinstance(data, dict):
                raise ValueError("Expected an API response object")
            if is_ollama:
                if data.get("done") is not True:
                    raise ValueError("Expected a completed non-streaming Ollama response")
                finish_reason = data.get("done_reason")
                message = data.get("message")
            else:
                choices = data.get("choices")
                if not isinstance(choices, list) or not choices or not isinstance(choices[0], dict):
                    raise ValueError("Expected a non-empty choices array")
                choice = choices[0]
                finish_reason = choice.get("finish_reason")
                message = choice.get("message")
            if not isinstance(message, dict):
                raise ValueError("Expected a message object")
            if message.get("refusal"):
                raise ServiceError("LLM_REFUSAL", "LLM отказалась сформировать ответ.", 502)
            # Some compatible APIs omit finish_reason. When supplied, only a
            # completed normal response is usable, even if its JSON parses.
            if finish_reason == "content_filter":
                raise ServiceError("LLM_REFUSAL", "LLM отказалась сформировать ответ.", 502)
            if finish_reason is not None and finish_reason != "stop":
                raise ValueError("LLM response did not finish normally")
            raw = message.get("content")
            if not isinstance(raw, str):
                raise ValueError("message.content must be string")
            result = json.loads(raw, parse_constant=_reject_json_constant)
            if not isinstance(result, dict):
                raise ValueError("Expected a JSON object")
            return result
        except (ValueError, TypeError) as exc:
            raise ServiceError("LLM_BAD_RESPONSE", "LLM вернула некорректный JSON или неполный ответ.", 502) from exc
