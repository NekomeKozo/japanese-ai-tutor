import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.errors import TutorError
from app.llm.base import Message
from app.llm.openai import OpenAIProvider
from app.tutor.schemas import TutorResponse
from tests.conftest import sample_response


def run_provider(settings, handler):
    settings.openai_api_key = SecretStr('test-key-not-real')

    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await OpenAIProvider(settings, client).generate(instructions='Teach Japanese',
                messages=[Message('user', 'こんにちは')], schema=TutorResponse.model_json_schema())
    return asyncio.run(run())


def test_openai_payload_and_extraction(settings):
    def handler(request):
        body = json.loads(request.content)
        assert str(request.url) == 'https://api.openai.com/v1/responses'
        assert request.headers['authorization'] == 'Bearer test-key-not-real'
        assert body['store'] is False
        assert body['input'] == [{'role': 'user', 'content': 'こんにちは'}]
        assert body['text']['format']['strict'] is True
        assert body['text']['format']['schema']['additionalProperties'] is False
        return httpx.Response(200, json={'status': 'completed', 'output': [
            {'type': 'reasoning', 'summary': []},
            {'type': 'message', 'content': [{'type': 'output_text', 'text': json.dumps(sample_response())}]}]})
    assert json.loads(run_provider(settings, handler)) == sample_response()


@pytest.mark.parametrize('status,code', [(401, 'provider_auth'), (403, 'provider_auth'), (429, 'provider_rate_limit'), (500, 'provider_failure'), (400, 'provider_failure')])
def test_provider_http_errors(settings, status, code):
    with pytest.raises(TutorError) as caught:
        run_provider(settings, lambda request: httpx.Response(status, text='PRIVATE_PROVIDER_BODY'))
    assert caught.value.code == code
    assert 'PRIVATE' not in str(caught.value)


@pytest.mark.parametrize('payload,code', [
    ({'status': 'incomplete'}, 'incomplete_response'),
    ({'status': 'completed', 'output': []}, 'invalid_model_response'),
    ({'status': 'completed', 'output': None}, 'invalid_model_response'),
    ([], 'invalid_model_response'),
    ({'status': 'completed', 'output': [{'type': 'message', 'content': [{'type': 'refusal'}]}]}, 'provider_refusal'),
])
def test_bad_provider_envelopes(settings, payload, code):
    with pytest.raises(TutorError) as caught:
        run_provider(settings, lambda request: httpx.Response(200, json=payload))
    assert caught.value.code == code


def test_non_json_provider_body(settings):
    with pytest.raises(TutorError, match='unreadable'):
        run_provider(settings, lambda request: httpx.Response(200, text='<html>bad gateway</html>'))


@pytest.mark.parametrize('error,code', [(httpx.ReadTimeout, 'provider_timeout'), (httpx.ConnectError, 'provider_unavailable')])
def test_network_errors(settings, error, code):
    def handler(request):
        raise error('internal network details', request=request)
    with pytest.raises(TutorError) as caught:
        run_provider(settings, handler)
    assert caught.value.code == code
