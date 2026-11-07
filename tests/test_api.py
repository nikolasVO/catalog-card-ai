import json

from fastapi.testclient import TestClient

from app.main import app, get_service
from app.schemas import ProductInput
from app.service import CardService
from unittest.mock import AsyncMock

client=TestClient(app)


def test_ui_and_health():
    assert client.get('/').status_code == 200
    assert 'Draftly' in client.get('/').text
    assert client.get('/api/health').json() == {'status':'ok'}
    assert len(client.get('/api/examples').json()) == 2
    assert client.get('/api/examples/tachometer/draft').status_code == 200
    assert client.get('/api/examples/unknown/draft').status_code == 404


def test_bad_json_and_empty_name():
    resp=client.post('/api/generate', content='{"name":',headers={'Content-Type':'application/json'})
    assert resp.status_code == 422
    assert client.post('/api/generate',json={'name':'  '}).status_code == 422
    assert client.post('/api/generate',json={'name':'OK','specs':['wrong']}).status_code == 422
    assert client.post('/api/generate',json={'name':'OK','specs':{'x':[]}}).status_code == 422


def test_missing_data_returns_needs_data_without_key():
    resp=client.post('/api/generate',json={'name':'Термометр','specs':{}})
    assert resp.status_code == 200
    card=resp.json()
    assert card['status']=='needs_data'
    assert card['key_characteristics'][1]['value']=='данных нет'
    assert 'Технические характеристики' in card['missing_fields']


def test_good_api_draft_with_fake_llm(products, example_cards):
    fake_llm=AsyncMock()
    fake_llm.generate.return_value = {k:example_cards[0][k] for k in ('seo_title','seo_description','search_queries','commercial_block')}
    app.dependency_overrides[get_service] = lambda: CardService(fake_llm)
    try:
        resp=client.post('/api/generate',json=products[0].model_dump())
        assert resp.status_code == 200
        assert resp.json()['seo_title']==example_cards[0]['seo_title']
        md=client.post('/api/generate/markdown',json=products[0].model_dump())
        assert md.status_code==200
        assert '## Характеристики' in md.text
    finally:
        app.dependency_overrides.clear()
