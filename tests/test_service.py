from unittest.mock import AsyncMock

import pytest

from app.errors import ServiceError
from app.markdown import as_markdown
from app.schemas import ProductInput
from app.service import CardService, factual_characteristics
from app.validators import unsupported_numbers


@pytest.mark.asyncio
async def test_two_products_have_grounded_cards(products, example_cards):
    for product, expected in zip(products, example_cards):
        mock = AsyncMock()
        mock.generate.return_value = {k: expected[k] for k in ('seo_title','seo_description','search_queries','commercial_block')}
        card = await CardService(mock).generate(product)
        assert card.status == 'draft'
        assert 800 <= len(card.seo_description) <= 1200
        assert len(card.seo_title) <= 70
        assert len(card.search_queries) in (3,4,5)
        assert card.requires_editor_review
        assert all(c.value in list(product.specs.values()) + [product.name, product.manufacturer, 'данных нет']
                   for c in card.key_characteristics)
        assert 'данных нет' in as_markdown(card)
        mock.generate.assert_awaited_once()


@pytest.mark.asyncio
async def test_incomplete_input_skips_llm():
    llm = AsyncMock()
    product = ProductInput(name='Манометр неизвестной модели', manufacturer='', specs={'Диапазон':'', 'Питание':None}, expected_specs=['Класс точности'])
    card = await CardService(llm).generate(product)
    assert card.status == 'needs_data'
    assert card.seo_description == ''
    assert 'Класс точности' in card.missing_fields
    assert any(c.value == 'данных нет' for c in card.key_characteristics)
    llm.generate.assert_not_awaited()


@pytest.mark.asyncio
async def test_new_number_causes_second_try_and_final_error(products, example_cards):
    source = example_cards[0]
    copy = {k: source[k] for k in ('seo_title','seo_description','search_queries','commercial_block')}
    copy['commercial_block'] += ' Точность 77777.'
    llm = AsyncMock()
    llm.generate.return_value = copy
    with pytest.raises(ServiceError) as exc:
        await CardService(llm).generate(products[0])
    assert exc.value.code == 'LLM_OUTPUT_INVALID'
    assert llm.generate.await_count == 2


@pytest.mark.asyncio
async def test_invalid_length_causes_retry_and_recovery(products, example_cards):
    good = {k: example_cards[0][k] for k in ('seo_title','seo_description','search_queries','commercial_block')}
    bad = {**good, 'seo_description':'Слишком коротко'}
    llm = AsyncMock()
    llm.generate.side_effect = [bad, good]
    card = await CardService(llm).generate(products[0])
    assert card.status == 'draft'
    assert llm.generate.await_count == 2
    assert 'min_length' in llm.generate.await_args.kwargs['correction'] or '800' in llm.generate.await_args.kwargs['correction']


def test_missing_spec_is_explicit(products):
    for product in products:
        characteristics, missing = factual_characteristics(product)
        assert 'Класс точности' in missing
        assert next(c for c in characteristics if c.name == 'Класс точности').value == 'данных нет'


def test_numeric_grounding(products, example_cards):
    for product, card in zip(products, example_cards):
        fields = [card['seo_title'],card['seo_description'],card['commercial_block'],*card['search_queries']]
        assert unsupported_numbers(product,fields) == set()
    assert unsupported_numbers(products[0],['Гарантия 900 лет']) == {'900'}
