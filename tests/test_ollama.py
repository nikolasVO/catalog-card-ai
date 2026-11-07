"""Native Ollama requests, completion checks, and key-free live-smoke entrypoint."""
import json
from unittest.mock import AsyncMock

import httpx
import pytest

from app.config import Settings
from app.errors import ServiceError
from app.llm import LLMClient
from app.prompts import RESPONSE_SCHEMA
from app.schemas import CardOutput


def ollama_settings(api_key=""):
    return Settings(
        api_key, "unused-openai-model", "https://unused-openai.example/v1", 180,
        provider="ollama", ollama_base_url="http://127.0.0.1:11434", ollama_model="qwen3.5:9b",
    )


@pytest.mark.asyncio
async def test_native_payload_and_response_without_sending_an_api_key(products, example_cards):
    expected = {key: example_cards[0][key] for key in (
        "seo_title", "seo_description", "search_queries", "commercial_block",
    )}
    requests = []

    def handler(request):
        requests.append(request)
        payload = json.loads(request.content)
        assert str(request.url) == "http://127.0.0.1:11434/api/chat"
        assert "authorization" not in request.headers
        assert "must-not-be-sent" not in request.content.decode()
        assert payload["model"] == "qwen3.5:9b"
        assert payload["think"] is False
        assert payload["stream"] is False
        assert payload["format"] == RESPONSE_SCHEMA["json_schema"]["schema"]
        assert payload["options"] == {"temperature": 0, "num_predict": 2500, "num_ctx": 8192}
        assert "response_format" not in payload
        assert "keep_alive" not in payload
        return httpx.Response(200, json={
            "message": {"role": "assistant", "content": json.dumps(expected, ensure_ascii=False)},
            "done": True,
            "done_reason": "stop",
        })

    client = LLMClient(ollama_settings("must-not-be-sent"), transport=httpx.MockTransport(handler))
    assert await client.generate(products[0]) == expected
    assert len(requests) == 1


@pytest.mark.asyncio
async def test_native_provider_needs_no_key(products):
    client = LLMClient(ollama_settings(), transport=httpx.MockTransport(lambda _request: httpx.Response(
        200, json={"message": {"content": '{"seo_title":"ok"}'}, "done": True, "done_reason": "stop"},
    )))
    assert await client.generate(products[0]) == {"seo_title": "ok"}


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    {"done": True, "message": None},
    {"done": True, "message": []},
    {"done": True, "message": {"content": []}},
    {"done": True, "message": {"content": "[]"}},
    {"done": False, "message": {"content": '{}'}},
    {"done": "true", "message": {"content": '{}'}},
    {"message": {"content": '{}'}},
    {"done": True, "done_reason": "length", "message": {"content": '{}'}},
    {"done": True, "message": {"content": '{"score":Infinity}'}},
])
async def test_native_provider_rejects_incomplete_or_malformed_responses(products, body):
    client = LLMClient(ollama_settings(), transport=httpx.MockTransport(
        lambda _request: httpx.Response(200, json=body),
    ))
    with pytest.raises(ServiceError) as exc:
        await client.generate(products[0])
    assert exc.value.code == "LLM_BAD_RESPONSE"
    assert exc.value.http_status == 502


def test_native_settings_from_env(monkeypatch):
    monkeypatch.setattr("app.config.load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434/")
    monkeypatch.setenv("OLLAMA_MODEL", "qwen3.5:27b-q4_K_M")
    monkeypatch.delenv("LLM_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    settings = Settings.from_env()
    assert settings.provider == "ollama"
    assert settings.api_key == ""
    assert settings.active_model == "qwen3.5:27b-q4_K_M"
    assert settings.ollama_base_url == "http://127.0.0.1:11434"
    assert settings.timeout_seconds == 180


def test_invalid_provider_is_a_safe_configuration_error(monkeypatch):
    monkeypatch.setattr("app.config.load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("LLM_PROVIDER", "private-invalid-provider")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "40")
    with pytest.raises(ServiceError) as exc:
        Settings.from_env()
    assert exc.value.code == "CONFIG_INVALID"
    assert "private-invalid-provider" not in exc.value.message


def test_invalid_native_url_is_rejected(monkeypatch):
    monkeypatch.setattr("app.config.load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("LLM_PROVIDER", "ollama")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "180")
    monkeypatch.setenv("OLLAMA_BASE_URL", "file:///private-ollama-path")
    with pytest.raises(ServiceError) as exc:
        Settings.from_env()
    assert exc.value.code == "CONFIG_INVALID"
    assert "OLLAMA_BASE_URL" in exc.value.message
    assert "private-ollama-path" not in exc.value.message


@pytest.mark.asyncio
async def test_live_smoke_does_not_skip_native_provider_without_a_key(tmp_path, monkeypatch, example_cards):
    from scripts import live_smoke

    monkeypatch.setattr(live_smoke.Settings, "from_env", lambda: ollama_settings())
    service = AsyncMock()
    service.generate.side_effect = [CardOutput.model_validate(card) for card in example_cards]
    monkeypatch.setattr(live_smoke, "CardService", lambda _client: service)
    assert await live_smoke.generate_all(tmp_path) == 0
    assert service.generate.await_count == 2
    assert (tmp_path / "tachometer.json").is_file()
    assert (tmp_path / "temperature-monitor.md").is_file()
    from scripts.verify_examples import verify_manifest

    verify_manifest(tmp_path)
    manifest = json.loads((tmp_path / "manifest.json").read_text())
    assert manifest["provider"] == "ollama"
    assert manifest["model"] == "qwen3.5:9b"
    assert len(manifest["records"]) == 2
    output = tmp_path / "tachometer.json"
    output.write_text(output.read_text() + "\n")
    with pytest.raises(AssertionError, match="Live response changed"):
        verify_manifest(tmp_path)
