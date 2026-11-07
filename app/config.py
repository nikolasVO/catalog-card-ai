"""Environment-only configuration. No tokens are stored in the repository."""
from dataclasses import dataclass
import math
import os
from pathlib import Path
from urllib.parse import urlsplit

from dotenv import load_dotenv

from app.errors import ServiceError

ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Settings:
    api_key: str
    model: str
    base_url: str
    timeout_seconds: float
    provider: str = "openai"
    ollama_base_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3.5:9b"

    def __post_init__(self) -> None:
        if self.provider not in {"openai", "ollama"}:
            raise ServiceError("CONFIG_INVALID", "LLM_PROVIDER должен быть openai или ollama.", 503)
        if (
            isinstance(self.timeout_seconds, bool)
            or not isinstance(self.timeout_seconds, (int, float))
            or not math.isfinite(self.timeout_seconds)
            or self.timeout_seconds <= 0
        ):
            raise ServiceError(
                "CONFIG_INVALID",
                "LLM_TIMEOUT_SECONDS должно быть положительным конечным числом.",
                503,
            )
        try:
            base_url = self.ollama_base_url if self.provider == "ollama" else self.base_url
            url = urlsplit(base_url)
            port = url.port  # Access validates malformed and out-of-range ports.
            valid_url = (
                url.scheme in {"http", "https"}
                and bool(url.hostname)
                and not url.username and not url.password
                and not url.query and not url.fragment
                and not any(character.isspace() or ord(character) < 32 or ord(character) == 127 for character in base_url)
                and (port is None or port > 0)
            )
        except (ValueError, TypeError):
            valid_url = False
        if not valid_url:
            variable = "OLLAMA_BASE_URL" if self.provider == "ollama" else "OPENAI_BASE_URL"
            raise ServiceError(
                "CONFIG_INVALID",
                f"{variable} должен быть HTTP(S)-адресом API без логина, пароля и параметров запроса.",
                503,
            )

    @property
    def active_model(self) -> str:
        return self.ollama_model if self.provider == "ollama" else self.model

    @classmethod
    def from_env(cls) -> "Settings":
        load_dotenv(ROOT / ".env", override=False)
        provider = os.getenv("LLM_PROVIDER", "openai").strip().casefold()
        try:
            timeout = float(os.getenv("LLM_TIMEOUT_SECONDS", "180" if provider == "ollama" else "40"))
        except ValueError as exc:
            raise ServiceError(
                "CONFIG_INVALID",
                "LLM_TIMEOUT_SECONDS должно быть положительным конечным числом.",
                503,
            ) from exc
        return cls(
            api_key=os.getenv("OPENAI_API_KEY", "").strip(),
            model=os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip() or "gpt-4o-mini",
            base_url=os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1").strip().rstrip("/"),
            timeout_seconds=timeout,
            provider=provider,
            ollama_base_url=os.getenv("OLLAMA_BASE_URL", "http://127.0.0.1:11434").strip().rstrip("/"),
            ollama_model=os.getenv("OLLAMA_MODEL", "qwen3.5:9b").strip() or "qwen3.5:9b",
        )
