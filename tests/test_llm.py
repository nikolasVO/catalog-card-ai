import json

import httpx
import pytest

from app.config import Settings
from app.errors import ServiceError
from app.llm import LLMClient


@pytest.mark.asyncio
async def test_http_payload_structure_and_no_key_in_body(products, example_cards):
    captured=[]
    def handler(req):
        captured.append(req)
        payload=json.loads(req.content)
        assert payload['model']=='gpt-4o-mini'
        assert payload['response_format']['json_schema']['strict'] is True
        assert 'JSON' in payload['messages'][0]['content']
        assert 'ТХ01-224.Щ2.Р-RS' in payload['messages'][1]['content']
        assert 'test-secret' not in req.content.decode()
        return httpx.Response(200,json={'choices':[{'message':{'content':json.dumps({k:example_cards[0][k] for k in ('seo_title','seo_description','search_queries','commercial_block')},ensure_ascii=False)}}]})
    client=LLMClient(Settings('test-secret','gpt-4o-mini','https://api.openai.com/v1',5),transport=httpx.MockTransport(handler))
    resp=await client.generate(products[0])
    assert resp['seo_title']==example_cards[0]['seo_title']
    assert captured[0].headers['authorization']=='Bearer test-secret'


@pytest.mark.asyncio
async def test_auth_error_is_sanitized(products):
    client=LLMClient(Settings('wrong','gpt-4o-mini','https://api.openai.com/v1',5),transport=httpx.MockTransport(lambda req: httpx.Response(401,json={'error':'secret info'})))
    with pytest.raises(ServiceError) as exc:
        await client.generate(products[0])
    assert exc.value.code=='LLM_AUTH'
    assert 'secret' not in exc.value.message


@pytest.mark.asyncio
async def test_retries_on_429_then_success(products):
    num=0
    def handler(req):
        nonlocal num
        num += 1
        if num < 3:
            return httpx.Response(429)
        return httpx.Response(200,json={'choices':[{'message':{'content':'{"seo_title": "ok"}'}}]})
    client=LLMClient(Settings('key','gpt-4o-mini','https://api.openai.com/v1',5),transport=httpx.MockTransport(handler))
    assert await client.generate(products[0]) == {'seo_title':'ok'}
    assert num == 3


@pytest.mark.asyncio
async def test_no_api_key(products):
    client=LLMClient(Settings('','gpt-4o-mini','https://api.openai.com/v1',5))
    with pytest.raises(ServiceError) as exc:
        await client.generate(products[0])
    assert exc.value.code=='API_KEY_MISSING'
