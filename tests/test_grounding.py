"""Regression cases that reused-number checks alone cannot detect."""
from copy import deepcopy
from unittest.mock import AsyncMock

import pytest

from app.errors import ServiceError
from app.schemas import ProductInput
from app.service import CardService
from app.validators import unsupported_claims, unsupported_numbers, unsupported_quantities


def test_error_percentage_cannot_become_accuracy_class():
    product = ProductInput(
        name="Манометр", specs={"Погрешность": "±0,5 %"}, expected_specs=["Класс точности"],
    )
    invented = ["Класс точности прибора — 0,5."]
    assert unsupported_numbers(product, invented) == set()
    assert "Класс точности" in unsupported_claims(product, invented)
    assert not unsupported_claims(product, ["Класс точности требует уточнения."])
    assert "Класс точности" in unsupported_claims(product, ["Класс точности 0,5 требует уточнения."])
    assert "Класс точности" in unsupported_claims(product, ["0,5 — класс точности, требуется уточнение."])


@pytest.mark.parametrize("value", ["", "данных нет", "нет", "отсутствует", "не поддерживается"])
def test_empty_or_negative_interface_is_not_positive_evidence(value):
    product = ProductInput(name="Измеритель", specs={"Wi-Fi": value})
    assert "Wi-Fi" in unsupported_claims(product, ["Прибор поддерживает Wi-Fi."])


def test_negative_description_does_not_confirm_support():
    product = ProductInput(name="Измеритель", description="Wi-Fi отсутствует. Bluetooth не поддерживается.")
    assert unsupported_claims(product, ["Есть Wi-Fi и Bluetooth."]) == {"Wi-Fi", "Bluetooth"}
    assert not unsupported_claims(product, ["Wi-Fi отсутствует."])


def test_missing_notice_cannot_authorize_another_assertion():
    product = ProductInput(name="Измеритель")
    assert "Wi-Fi" in unsupported_claims(product, ["Класс точности не указан, но прибор поддерживает Wi-Fi."])
    assert "Wi-Fi" in unsupported_claims(product, ["Класс точности не указан и прибор поддерживает Wi-Fi."])


def test_supported_material_allows_inflection_but_not_substitution():
    product = ProductInput(name="Измеритель", specs={"Материал корпуса": "нержавеющая сталь"})
    assert not unsupported_claims(product, ["Корпус из нержавеющей стали."])
    assert "материал корпуса" in unsupported_claims(product, ["Корпус пластиковый."])


def test_ip_code_must_match_instead_of_reusing_dimension(products):
    product = products[1]
    assert not unsupported_numbers(product, ["Защита передней панели IP96."])
    assert "защита IP" in unsupported_claims(product, ["Защита передней панели IP96."])
    assert not unsupported_claims(product, ["Защита передней панели IP54."])
    assert "защита IP" in unsupported_claims(product, ["Защита передней панели IPX4."])
    assert "защита IP" in unsupported_claims(product, ["Защита передней панели IР96."])


def test_interface_version_cannot_hide_or_change_support(products):
    assert "Wi-Fi" in unsupported_claims(products[1], ["Поддерживает Wi-Fi6."])
    product = ProductInput(name="Измеритель", specs={"Интерфейс": "USB 2.0"})
    assert "USB" in unsupported_claims(product, ["Есть USB3.0."])
    assert not unsupported_claims(product, ["Есть USB2.0."])


def test_supplied_accuracy_class_cannot_reuse_error_percentage():
    product = ProductInput(name="Манометр", specs={"Класс точности": "1,5", "Погрешность": "±0,5 %"})
    assert "Класс точности" in unsupported_claims(product, ["Класс точности прибора — 0,5."])
    assert not unsupported_claims(product, ["Класс точности — 1,5."])


@pytest.mark.parametrize("text", [
    "Питание — 90–264 А.",
    "Питание — 264–90 В.",
    "Температура эксплуатации — 20…70 °C.",
    "Питание — 220 В.",  # This voltage belongs to the relay, not the power supply.
])
def test_quantities_cannot_change_unit_range_sign_or_attribute(products, text):
    assert unsupported_quantities(products[0], [text])


@pytest.mark.parametrize("text", [
    "Питание — 90–264 В или 20–34 В.",
    "Температура эксплуатации — -20…+70 °C.",
    "Диапазон частоты вращения — от 150 до 150 000 об/мин.",
])
def test_original_quantities_and_typographic_variants_are_allowed(products, text):
    assert not unsupported_quantities(products[0], [text])


def test_unknown_expected_field_accepts_only_missing_notice(products):
    source = products[0].model_dump()
    source["expected_specs"] += ["Срок службы"]
    product = ProductInput.model_validate(source)
    assert "Срок службы" in unsupported_claims(product, ["Срок службы — 20 лет."])
    assert not unsupported_claims(product, ["Срок службы требует уточнения."])


def test_empty_key_does_not_authorize_its_number():
    product = ProductInput(name="Измеритель", specs={"RS-485": ""})
    assert unsupported_numbers(product, ["RS-485"]) == {"485"}


@pytest.mark.asyncio
@pytest.mark.parametrize("replacement", [
    "Класс точности прибора — 0,4. Прибор подходит для задач промышленного контроля.",
    "Защита передней панели — IP96. Прибор подходит для многозонного контроля температуры.",
    "Питание прибора — 230 В. Прибор подходит для многозонного контроля температуры.",
])
async def test_invalid_but_reused_values_retry_and_never_become_draft(products, example_cards, replacement):
    copy = {key: deepcopy(example_cards[1][key]) for key in (
        "seo_title", "seo_description", "search_queries", "commercial_block",
    )}
    copy["commercial_block"] = replacement
    llm = AsyncMock()
    llm.generate.return_value = copy
    with pytest.raises(ServiceError) as error:
        await CardService(llm).generate(products[1])
    assert error.value.code == "LLM_OUTPUT_INVALID"
    assert llm.generate.await_count == 2


@pytest.mark.asyncio
async def test_unsupported_interface_retries_even_when_key_was_supplied(products, example_cards):
    source = products[0].model_dump()
    source["specs"]["Wi-Fi"] = ""
    product = ProductInput.model_validate(source)
    copy = {key: example_cards[0][key] for key in (
        "seo_title", "seo_description", "search_queries", "commercial_block",
    )}
    copy["commercial_block"] += " Поддерживается Wi-Fi."
    llm = AsyncMock()
    llm.generate.return_value = copy
    with pytest.raises(ServiceError):
        await CardService(llm).generate(product)
    assert llm.generate.await_count == 2
