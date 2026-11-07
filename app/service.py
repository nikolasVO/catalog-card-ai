"""Orchestration: trusted facts stay deterministic; LLM writes editorial fields only."""
from typing import Protocol

from pydantic import ValidationError

from app.errors import ServiceError
from app.schemas import CardOutput, Characteristic, GeneratedText, MISSING_MARKERS, ProductInput
from app.validators import unsupported_claims, unsupported_numbers, unsupported_quantities


class CopyGenerator(Protocol):
    async def generate(self, product: ProductInput, correction: str = "") -> dict: ...


def _present(value: str | None) -> bool:
    return bool(value and value.strip().casefold() not in MISSING_MARKERS)


def factual_characteristics(product: ProductInput) -> tuple[list[Characteristic], list[str]]:
    result = [
        Characteristic(name="Название", value=product.name, verified=True),
        Characteristic(name="Производитель", value=product.manufacturer if _present(product.manufacturer) else "данных нет", verified=_present(product.manufacturer)),
    ]
    missing: list[str] = []
    if not _present(product.manufacturer):
        missing.append("Производитель")
    if not _present(product.description):
        missing.append("Описание / фрагмент паспорта")
    keys_present: set[str] = set()
    for key, val in product.specs.items():
        has_value = _present(val)
        result.append(Characteristic(name=key, value=val if has_value else "данных нет", verified=has_value))
        keys_present.add(key.casefold())
        if not has_value:
            missing.append(key)
    for key in product.expected_specs:
        if key.casefold() not in keys_present:
            result.append(Characteristic(name=key, value="данных нет", verified=False))
            missing.append(key)
    if not product.specs:
        missing.append("Технические характеристики")
    return result, missing


def correction_hint(error: ValidationError | ValueError, raw: dict) -> str:
    """Give the model actionable limits without echoing its rejected prose."""
    if isinstance(error, ValidationError):
        issues = []
        for detail in error.errors(include_input=False):
            field = str(detail["loc"][0]) if detail["loc"] else "ответ"
            value = raw.get(field)
            length = f"; получено {len(value)} символов" if isinstance(value, str) else ""
            issues.append(f"{field}: {detail['msg']}{length}")
        message = "; ".join(issues)
    else:
        message = str(error)
    return (
        message[:1100]
        + ". Верни весь JSON заново. SEO-описание сократи или дополни до 950–1050 символов "
          "с пробелами, выбрав только основные факты. Заголовок: производитель и модель, максимум 70 символов."
    )


class CardService:
    def __init__(self, llm: CopyGenerator):
        self.llm = llm

    async def generate(self, product: ProductInput) -> CardOutput:
        characteristics, missing = factual_characteristics(product)
        verified_specs = sum(ch.verified for ch in characteristics[2:])
        insufficient = verified_specs < 4 and len((product.description or "").strip()) < 100
        if insufficient:
            return CardOutput(
                status="needs_data",
                product_name=product.name,
                manufacturer=product.manufacturer or "данных нет",
                seo_title="",
                seo_description="",
                key_characteristics=characteristics,
                search_queries=[],
                commercial_block="",
                missing_fields=missing + ["Недостаточно фактов для текста на 800–1200 символов"],
                warnings=["Генерация пропущена: без подтверждённых сведений текст был бы недостоверным."],
                source_url=product.source_url,
                source_id=product.source_id,
            )

        correction = ""
        for attempt in range(2):
            raw = await self.llm.generate(product, correction=correction)
            try:
                copy = GeneratedText.model_validate(raw)
                if product.name.casefold() not in copy.seo_title.casefold() and len(product.name) <= 55:
                    raise ValueError("SEO-заголовок не содержит полного названия модели")
                fields = [copy.seo_title, copy.seo_description, copy.commercial_block, *copy.search_queries]
                numbers = unsupported_numbers(product, fields)
                if numbers:
                    raise ValueError("в тексте появились неподтверждённые числа: " + ", ".join(sorted(numbers)))
                quantities = unsupported_quantities(product, fields)
                if quantities:
                    raise ValueError("не подтверждены технические значения: " + ", ".join(sorted(quantities)))
                claims = unsupported_claims(product, fields)
                if claims:
                    raise ValueError("в тексте появились неподтверждённые утверждения: " + ", ".join(sorted(claims)))
            except (ValidationError, ValueError) as exc:
                correction = correction_hint(exc, raw)
                if attempt == 0:
                    continue
                raise ServiceError(
                    "LLM_OUTPUT_INVALID",
                    "LLM дважды нарушила требования формата или достоверности. Измените входные данные или повторите запрос.",
                    502,
                ) from exc
            return CardOutput(
                status="draft",
                product_name=product.name,
                manufacturer=product.manufacturer or "данных нет",
                seo_title=copy.seo_title,
                seo_description=copy.seo_description,
                key_characteristics=characteristics,
                search_queries=copy.search_queries,
                commercial_block=copy.commercial_block,
                missing_fields=missing,
                warnings=(
                    ["Часть параметров отсутствует в источнике; требуется уточнение перед публикацией."]
                    if missing else []
                ) + ["Числа, единицы, диапазоны и отдельные технические утверждения сверены с входом; смысл проверяет редактор."],
                source_url=product.source_url,
                source_id=product.source_id,
            )
        raise RuntimeError("Unreachable")
