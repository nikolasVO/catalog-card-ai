"""Input and output contracts exposed by HTTP API and CLI."""
import math
from typing import Any, Literal
from urllib.parse import urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


MISSING_MARKERS = {
    "", "-", "—", "нет", "неизвестно", "данных нет", "n/a", "null", "none",
    "не указан", "не указана", "не указано", "неизвестен", "неизвестна",
}


class ProductInput(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    name: str = Field(min_length=1, max_length=180)
    manufacturer: str | None = None
    product_type: str | None = None
    specs: dict[str, str] = Field(default_factory=dict)
    expected_specs: list[str] = Field(default_factory=list)
    description: str | None = Field(default=None, max_length=12000)
    source_url: str | None = None
    source_id: str | None = None

    @field_validator("name")
    @classmethod
    def name_not_blank(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("название товара не может быть пустым")
        return value.strip()

    @field_validator("specs", mode="before")
    @classmethod
    def normalize_specs(cls, value: Any) -> dict[str, str]:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise ValueError("specs должен быть JSON-объектом")
        normalized: dict[str, str] = {}
        for key, val in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValueError("каждое название характеристики должно быть строкой")
            if len(key) > 120:
                raise ValueError("название характеристики слишком длинное")
            if val is None:
                normalized[key.strip()] = ""
            elif isinstance(val, str):
                if len(val.strip()) > 1200:
                    raise ValueError("значение характеристики слишком длинное (не более 1200 символов)")
                normalized[key.strip()] = val.strip()
            elif isinstance(val, (int, float)) and not isinstance(val, bool):
                if isinstance(val, float) and not math.isfinite(val):
                    raise ValueError("числовое значение характеристики должно быть конечным")
                normalized[key.strip()] = str(val)
            else:
                raise ValueError("значение характеристики должно быть строкой, числом или null")
        if len(normalized) > 60:
            raise ValueError("слишком много характеристик (не более 60)")
        return normalized

    @field_validator("expected_specs")
    @classmethod
    def normalize_expected(cls, value: list[str]) -> list[str]:
        unique: list[str] = []
        for field in value:
            field = field.strip()
            if field and field.casefold() not in {x.casefold() for x in unique}:
                unique.append(field)
        if len(unique) > 30:
            raise ValueError("слишком много ожидаемых характеристик (не более 30)")
        return unique

    @field_validator("source_url")
    @classmethod
    def validated_source_url(cls, value: str | None) -> str | None:
        if value is None or not value.strip():
            return None
        url = urlsplit(value.strip())
        if url.scheme not in {"https", "http"} or not url.netloc or url.username or url.password:
            raise ValueError("source_url должен быть HTTP(S)-ссылкой без данных для входа")
        return value.strip()


class GeneratedText(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)

    seo_title: str = Field(min_length=5, max_length=70)
    seo_description: str = Field(min_length=800, max_length=1200)
    search_queries: list[str] = Field(min_length=3, max_length=5)
    commercial_block: str = Field(min_length=40, max_length=450)

    @field_validator("search_queries")
    @classmethod
    def valid_search_queries(cls, value: list[str]) -> list[str]:
        normalized = [query.strip() for query in value]
        if any(not q or len(q) > 120 for q in normalized):
            raise ValueError("поисковые запросы должны содержать 1–120 символов")
        if len({q.casefold() for q in normalized}) != len(normalized):
            raise ValueError("поисковые запросы не должны повторяться")
        return normalized


class Characteristic(BaseModel):
    name: str
    value: str
    verified: bool


class CardOutput(BaseModel):
    status: Literal["draft", "needs_data"]
    product_name: str
    manufacturer: str
    seo_title: str
    seo_description: str
    key_characteristics: list[Characteristic]
    search_queries: list[str]
    commercial_block: str
    missing_fields: list[str]
    warnings: list[str]
    source_url: str | None
    source_id: str | None
    requires_editor_review: bool = True
