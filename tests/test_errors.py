"""Regression coverage for invalid inputs and unusable provider responses."""
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.errors import ServiceError
from app.llm import LLMClient
from app.main import app, get_service
from app.service import CardService


@pytest.mark.parametrize("endpoint", ["/api/generate", "/api/generate/markdown"])
@pytest.mark.parametrize("token", ["NaN", "Infinity", "-Infinity"])
def test_nonfinite_input_returns_safe_validation_error(endpoint, token):
    body = (
        '{"name":"private-product-name","specs":{"range":' + token
        + '},"description":"private-passport-fragment"}'
    )
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post(endpoint, content=body, headers={"Content-Type": "application/json"})
    assert response.status_code == 422
    detail = response.json()["detail"]
    assert detail[0]["loc"] == ["body", "specs"]
    assert all(set(error) == {"loc", "msg", "type"} for error in detail)
    assert "private-product-name" not in response.text
    assert "private-passport-fragment" not in response.text


def test_validation_error_does_not_echo_extra_keys_or_values():
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/generate", json={
            "name": "private-product-name",
            "private-extra-field": {"secret": "private-extra-value"},
        })
    assert response.status_code == 422
    assert response.json()["detail"][0]["loc"] == ["body"]
    assert "private-" not in response.text


@pytest.mark.asyncio
@pytest.mark.parametrize("body", [
    None,
    [],
    {},
    {"choices": None},
    {"choices": {}},
    {"choices": []},
    {"choices": [None]},
    {"choices": [[]]},
    {"choices": [{"message": None}]},
    {"choices": [{"message": []}]},
    {"choices": [{"message": "private-provider-content"}]},
    {"choices": [{"message": {"content": None}}]},
    {"choices": [{"message": {"content": []}}]},
    {"choices": [{"message": {"content": "[]"}}]},
    {"choices": [{"message": {"content": '{"score":NaN}'}}]},
])
async def test_malformed_provider_shape_is_a_safe_domain_error(products, body):
    client = LLMClient(
        Settings("test-secret", "gpt-4o-mini", "https://api.example/v1", 5),
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json=body)),
    )
    with pytest.raises(ServiceError) as exc:
        await client.generate(products[0])
    assert exc.value.code == "LLM_BAD_RESPONSE"
    assert exc.value.http_status == 502
    assert "private-provider-content" not in exc.value.message
    assert "test-secret" not in exc.value.message


@pytest.mark.parametrize("message", [None, []])
def test_malformed_message_returns_http_502(products, message):
    client = LLMClient(
        Settings("test-secret", "gpt-4o-mini", "https://api.example/v1", 5),
        transport=httpx.MockTransport(lambda _request: httpx.Response(
            200, json={"choices": [{"message": message}]},
        )),
    )
    app.dependency_overrides[get_service] = lambda: CardService(client)
    try:
        with TestClient(app, raise_server_exceptions=False) as api:
            response = api.post("/api/generate", json=products[0].model_dump())
        assert response.status_code == 502
        assert response.json()["error"] == "LLM_BAD_RESPONSE"
        assert "test-secret" not in response.text
    finally:
        app.dependency_overrides.pop(get_service, None)


@pytest.mark.asyncio
@pytest.mark.parametrize("reason, expected_error", [
    ("length", "LLM_BAD_RESPONSE"),
    ("tool_calls", "LLM_BAD_RESPONSE"),
    ("content_filter", "LLM_REFUSAL"),
    ({"unexpected": "value"}, "LLM_BAD_RESPONSE"),
])
async def test_unfinished_response_is_rejected_even_with_valid_json(products, reason, expected_error):
    client = LLMClient(
        Settings("test-secret", "gpt-4o-mini", "https://api.example/v1", 5),
        transport=httpx.MockTransport(lambda _request: httpx.Response(200, json={
            "choices": [{"finish_reason": reason, "message": {"content": '{"seo_title":"ok"}'}}],
        })),
    )
    with pytest.raises(ServiceError) as exc:
        await client.generate(products[0])
    assert exc.value.code == expected_error


@pytest.mark.asyncio
async def test_provider_timeout_retries_and_returns_safe_error(products, monkeypatch):
    attempts = []

    def timeout(request):
        attempts.append(request)
        raise httpx.ReadTimeout("private-provider-detail", request=request)

    monkeypatch.setattr("app.llm.asyncio.sleep", AsyncMock())
    client = LLMClient(
        Settings("test-secret", "gpt-4o-mini", "https://api.example/v1", 5),
        transport=httpx.MockTransport(timeout),
    )
    with pytest.raises(ServiceError) as exc:
        await client.generate(products[0])
    assert len(attempts) == 3
    assert exc.value.code == "LLM_TIMEOUT"
    assert exc.value.http_status == 504
    assert "private-provider-detail" not in exc.value.message


@pytest.mark.asyncio
async def test_network_error_is_sanitized(products):
    def unavailable(request):
        raise httpx.ConnectError("private-network-detail", request=request)

    client = LLMClient(
        Settings("test-secret", "gpt-4o-mini", "https://api.example/v1", 5),
        transport=httpx.MockTransport(unavailable),
    )
    with pytest.raises(ServiceError) as exc:
        await client.generate(products[0])
    assert exc.value.code == "LLM_NETWORK"
    assert exc.value.http_status == 503
    assert "private-network-detail" not in exc.value.message


@pytest.mark.parametrize("timeout", ["private-invalid-timeout", "NaN", "Infinity", "0", "-1"])
def test_invalid_timeout_returns_safe_http_503(monkeypatch, timeout):
    monkeypatch.setattr("app.config.load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.example/v1")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", timeout)
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.post("/api/generate", json={"name": "Прибор"})
    assert response.status_code == 503
    assert response.json()["error"] == "CONFIG_INVALID"
    assert "private-invalid-timeout" not in response.text


@pytest.mark.parametrize("url", [
    "file:///private-provider-detail",
    "https://user:private-password@api.example/v1",
    "https://api.example:private-port/v1",
    "https://api.example:99999/v1",
    "https://api.example/v1?api_key=private-token",
])
def test_invalid_api_url_is_a_safe_configuration_error(monkeypatch, url):
    monkeypatch.setattr("app.config.load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_BASE_URL", url)
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "40")
    with pytest.raises(ServiceError) as exc:
        Settings.from_env()
    assert exc.value.code == "CONFIG_INVALID"
    assert exc.value.http_status == 503
    assert "private-" not in exc.value.message


def test_api_url_with_nul_is_a_safe_configuration_error():
    with pytest.raises(ServiceError) as exc:
        Settings("test-secret", "gpt-4o-mini", "https://api.example/\x00private-path", 40)
    assert exc.value.code == "CONFIG_INVALID"
    assert exc.value.http_status == 503
    assert "private-path" not in exc.value.message


def test_local_http_provider_is_supported(monkeypatch):
    monkeypatch.setattr("app.config.load_dotenv", lambda *_args, **_kwargs: None)
    monkeypatch.setenv("LLM_PROVIDER", "openai")
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:1234/v1/")
    monkeypatch.setenv("LLM_TIMEOUT_SECONDS", "40")
    assert Settings.from_env().base_url == "http://127.0.0.1:1234/v1"
