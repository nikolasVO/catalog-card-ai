"""Quality gates for the deliverables and simple hallucination defenses."""
from copy import deepcopy
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

from app.errors import ServiceError
from app.schemas import ProductInput
from app.service import CardService
from app.validators import unsupported_claims
from scripts.verify_examples import verify_files, verify_product


def test_bundled_examples_match_their_input_exactly():
    assert len(verify_files(Path(__file__).parents[1] / "examples" / "outputs")) == 2


def test_validator_rejects_unsupported_technologies_and_promises(products):
    product = products[1]
    assert unsupported_claims(product, ["Поддержка Bluetooth, Ethernet и Wi-Fi."]) == {"Bluetooth", "Ethernet", "Wi-Fi"}
    assert unsupported_claims(product, ["Гарантия 2 года, сертифицирован для монтажа."]) == {"гарантия", "сертификация"}
    assert unsupported_claims(product, ["Устройство поддерживает Modbus."]) == {"Modbus"}
    assert unsupported_claims(products[0], ["RS-485 / Modbus RTU/ASCII"]) == set()


@pytest.mark.asyncio
async def test_guarded_non_numeric_claim_retries_and_fails(products, example_cards):
    good = {key: example_cards[1][key] for key in ("seo_title", "seo_description", "search_queries", "commercial_block")}
    bad = {**good, "commercial_block": good["commercial_block"] + " Есть Bluetooth."}
    fake_llm = AsyncMock()
    fake_llm.generate.return_value = bad
    with pytest.raises(ServiceError) as exc:
        await CardService(fake_llm).generate(products[1])
    assert exc.value.code == "LLM_OUTPUT_INVALID"
    assert fake_llm.generate.await_count == 2
    assert "Bluetooth" in fake_llm.generate.await_args.kwargs["correction"]


@pytest.mark.asyncio
async def test_two_weak_specs_do_not_force_verbose_description():
    llm = AsyncMock()
    short = ProductInput(name="Промышленный прибор", specs={"Артикул": "X12", "Корпус": "пластик"}, description="Коротко")
    card = await CardService(llm).generate(short)
    assert card.status == "needs_data"
    llm.generate.assert_not_awaited()


def test_quality_gate_catches_modified_technical_value(products, example_cards):
    from app.schemas import CardOutput
    source = products[0]
    draft = deepcopy(example_cards[0])
    draft["key_characteristics"][2]["value"] = "измерение неизвестной величины"
    with pytest.raises(AssertionError):
        verify_product(source, CardOutput.model_validate(draft))


def test_no_silent_truncation_of_long_specs():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ProductInput(name="Прибор", specs={"Диапазон": "A" * 1201})
    with pytest.raises(ValidationError):
        ProductInput(name="Прибор", expected_specs=[f"Поле {i}" for i in range(31)])


def test_nonfinite_numeric_spec_rejected():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ProductInput(name="Прибор", specs={"Нагрузка": float("nan")})


def test_unsafe_source_url_rejected():
    from pydantic import ValidationError
    with pytest.raises(ValidationError):
        ProductInput(name="Прибор", source_url="javascript:alert(1)")
    with pytest.raises(ValidationError):
        ProductInput(name="Прибор", source_url="https://user:password@example.org/")
