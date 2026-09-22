import ast
import asyncio
import json
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.errors import TutorError
from app.llm.base import Message
from app.llm.factory import configuration_issue, create_provider, UnconfiguredProvider
from app.llm.gemini import GeminiProvider
from app.llm.openai import OpenAIProvider
from app.main import create_app
from app.tutor.schemas import TutorResponse
from tests.conftest import sample_response


def envelope(provider, text):
    if provider == 'gemini':
        return {'candidates': [{'finishReason': 'STOP', 'content': {'parts': [
            {'thought': True, 'text': 'private reasoning'}, {'text': text}]}}]}
    return {'status': 'completed', 'output': [{'type': 'message', 'content': [
        {'type': 'output_text', 'text': text}]}]}


def configure(settings, provider):
    settings.llm_provider = provider
    settings.llm_model = ''
    settings.gemini_api_key = SecretStr('fake-gemini-secret')
    settings.openai_api_key = SecretStr('fake-openai-secret')
    return settings


def run(settings, handler, schema=TutorResponse.model_json_schema()):
    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await create_provider(settings, client).generate(instructions='private instructions',
                messages=[Message('user', 'こんにちは'), Message('assistant', 'はい'),
                          Message('user', 'private question')], schema=schema)
    return asyncio.run(call())


@pytest.mark.parametrize('provider,adapter', [('gemini', GeminiProvider), ('openai', OpenAIProvider)])
def test_selection_and_only_selected_key_required(settings, provider, adapter):
    configure(settings, provider)
    setattr(settings, 'openai_api_key' if provider == 'gemini' else 'gemini_api_key', SecretStr(''))
    async def check():
        async with httpx.AsyncClient() as client:
            assert isinstance(create_provider(settings, client), adapter)
    asyncio.run(check())
    assert configuration_issue(settings) is None


@pytest.mark.parametrize('provider', ['gemini', 'openai'])
def test_payload_text_and_structured(settings, provider):
    configure(settings, provider)
    schema = TutorResponse.model_json_schema()
    for structured in (True, False):
        expected = json.dumps(sample_response()) if structured else '日本語を勉強しましょう。'
        def handler(request):
            body = json.loads(request.content)
            assert request.extensions['timeout']['read'] == settings.llm_timeout_seconds
            assert not request.url.query
            if provider == 'gemini':
                assert request.url.path == '/v1beta/models/gemini-3.1-flash-lite:generateContent'
                assert request.headers['x-goog-api-key'] == 'fake-gemini-secret'
                assert body['systemInstruction'] == {'parts': [{'text': 'private instructions'}]}
                assert body['contents'] == [
                    {'role': 'user', 'parts': [{'text': 'こんにちは'}]},
                    {'role': 'model', 'parts': [{'text': 'はい'}]},
                    {'role': 'user', 'parts': [{'text': 'private question'}]}]
                config = body['generationConfig']
                assert config['maxOutputTokens'] == settings.llm_max_output_tokens
                assert 'thinkingConfig' not in config
                if structured:
                    assert config['responseJsonSchema'] == schema
                    assert config['responseMimeType'] == 'application/json'
                else:
                    assert 'responseJsonSchema' not in config
            else:
                assert body['model'] == 'gpt-4.1-mini'
                assert body['instructions'] == 'private instructions'
                assert [m['content'] for m in body['input']] == ['こんにちは', 'はい', 'private question']
                assert body['text']['format']['type'] == ('json_schema' if structured else 'text')
            return httpx.Response(200, json=envelope(provider, expected))
        assert run(settings, handler, schema if structured else None) == expected


@pytest.mark.parametrize('provider', ['', 'unknown', 'private-bad-provider'])
def test_unconfigured_provider_is_safe(settings, provider, caplog):
    settings.llm_provider = provider
    with pytest.raises(TutorError) as caught:
        run(settings, lambda request: pytest.fail('Unexpected network request'))
    assert caught.value.code == 'provider_configuration'
    assert 'private-bad-provider' not in caplog.text
    assert 'provider_configuration' in caplog.text


@pytest.mark.parametrize('provider,adapter', [('gemini', GeminiProvider), ('openai', OpenAIProvider)])
def test_missing_keys(settings, provider, adapter):
    configure(settings, provider)
    setattr(settings, f'{provider}_api_key', SecretStr('  '))
    assert f'{provider.upper()}_API_KEY' in configuration_issue(settings)
    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: pytest.fail('Network'))) as client:
            assert isinstance(create_provider(settings, client), UnconfiguredProvider)
            with pytest.raises(TutorError) as caught:
                await adapter(settings, client).generate(instructions='', messages=[])
            assert caught.value.code == 'missing_api_key'
    asyncio.run(call())


@pytest.mark.parametrize('provider', ['gemini', 'openai'])
@pytest.mark.parametrize('status,code', [(400, 'provider_failure'), (401, 'provider_auth'),
    (403, 'provider_auth'), (429, 'provider_rate_limit'), (500, 'provider_failure')])
def test_http_failures_safe_logs(settings, provider, status, code, caplog):
    configure(settings, provider)
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(status, text='private response body')
    with pytest.raises(TutorError) as caught:
        run(settings, handler)
    assert caught.value.code == code
    assert len(calls) == 1  # No hidden retries or fallback to another provider.
    assert f'provider={provider} category={code}' in caplog.text
    for private in ['private', 'fake-gemini-secret', 'fake-openai-secret', 'Authorization', 'x-goog-api-key']:
        assert private not in caplog.text
        assert private not in str(caught.value)


@pytest.mark.parametrize('provider', ['gemini', 'openai'])
@pytest.mark.parametrize('exception,code', [(httpx.ReadTimeout, 'provider_timeout'),
    (httpx.ConnectError, 'provider_unavailable')])
def test_transport_failure(settings, provider, exception, code, caplog):
    configure(settings, provider)
    def handler(request):
        raise exception('private network detail', request=request)
    with pytest.raises(TutorError) as caught:
        run(settings, handler)
    assert caught.value.code == code
    assert 'private' not in caplog.text


@pytest.mark.parametrize('payload,code', [
    ([], 'invalid_model_response'), ({}, 'invalid_model_response'),
    ({'candidates': []}, 'invalid_model_response'),
    ({'candidates': None}, 'invalid_model_response'),
    ({'candidates': [{'finishReason': 'STOP', 'content': {'parts': []}}]}, 'invalid_model_response'),
    ({'candidates': [{'finishReason': 'MAX_TOKENS'}]}, 'incomplete_response'),
    ({'candidates': [{'finishReason': 'SAFETY'}]}, 'provider_refusal'),
    ({'promptFeedback': {'blockReason': 'SAFETY'}}, 'provider_refusal'),
    ({'candidates': [{'finishReason': 'STOP', 'content': {'parts': [{'text': 1}]}}]}, 'invalid_model_response'),
])
def test_gemini_bad_envelopes(settings, payload, code):
    configure(settings, 'gemini')
    with pytest.raises(TutorError) as caught:
        run(settings, lambda request: httpx.Response(200, json=payload))
    assert caught.value.code == code


@pytest.mark.parametrize('provider', ['gemini', 'openai'])
@pytest.mark.parametrize('raw', ['not JSON', '```json\n{}\n```', '{broken'])
def test_malformed_structured_text(settings, provider, raw):
    configure(settings, provider)
    with pytest.raises(TutorError) as caught:
        run(settings, lambda request: httpx.Response(200, json=envelope(provider, raw)))
    assert caught.value.code == 'invalid_model_response'


def test_gemini_non_json_http_body(settings):
    configure(settings, 'gemini')
    with pytest.raises(TutorError, match='unreadable'):
        run(settings, lambda request: httpx.Response(200, text='<html>gateway</html>'))


def test_environment_default_switch_and_model(monkeypatch):
    for key in ('LLM_PROVIDER', 'LLM_MODEL', 'GEMINI_API_KEY', 'OPENAI_API_KEY'):
        monkeypatch.delenv(key, raising=False)
    assert Settings(_env_file=None).llm_provider == 'gemini'
    for provider in ('gemini', 'openai'):
        monkeypatch.setenv('LLM_PROVIDER', provider)
        monkeypatch.setenv('LLM_MODEL', 'custom-model')
        monkeypatch.setenv(f'{provider.upper()}_API_KEY', 'fake-key')
        settings = Settings(_env_file=None)
        def handler(request):
            body = json.loads(request.content)
            if provider == 'gemini':
                assert 'custom-model:generateContent' in request.url.path
                assert 'thinkingConfig' not in body['generationConfig']
            else:
                assert body['model'] == 'custom-model'
            return httpx.Response(200, json=envelope(provider, '{}'))
        assert run(settings, handler) == '{}'


def test_invalid_model_never_becomes_url(settings):
    configure(settings, 'gemini')
    settings.llm_model = '../../private?key=secret'
    with pytest.raises(TutorError) as caught:
        run(settings, lambda request: pytest.fail('Network'))
    assert caught.value.code == 'provider_configuration'
    assert 'secret' not in caught.value.message


@pytest.mark.parametrize('provider', ['gemini', 'openai'])
def test_real_adapter_to_application_schema(settings, provider):
    configure(settings, provider)
    async def build():
        client = httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: httpx.Response(200, json=envelope(provider, json.dumps(sample_response())))))
        return client, create_provider(settings, client)
    http, adapter = asyncio.run(build())
    try:
        with TestClient(create_app(settings, adapter)) as client:
            session = client.post('/api/sessions').json()['session_id']
            response = client.post('/api/chat', json={'session_id': session, 'message': '日本を行きたいです。'})
            assert response.status_code == 200
            assert response.json()['response'] == sample_response()
            assert client.get('/api/health').json()['provider_configured'] is True
    finally:
        asyncio.run(http.aclose())


def test_learning_modules_do_not_import_provider_implementations():
    root = Path(__file__).resolve().parents[1] / 'app'
    for folder in ('tutor', 'assessment', 'learner', 'curriculum', 'memory'):
        for file in (root / folder).rglob('*.py'):
            tree = ast.parse(file.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                names = [node.module or ''] if isinstance(node, ast.ImportFrom) else (
                    [alias.name for alias in node.names] if isinstance(node, ast.Import) else [])
                assert not any(name.startswith(('openai', 'google', 'app.llm.openai', 'app.llm.gemini',
                                                'app.llm.factory')) for name in names), file
