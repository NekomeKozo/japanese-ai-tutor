import asyncio
import json

import httpx
import pytest
from pydantic import SecretStr

from app.config import ENV_FILE, PROJECT_ROOT, Settings
from app.errors import TutorError
from app.llm.common import log_http_failure, request_path
from app.llm.factory import provider_metadata
from app.llm.gemini import GeminiProvider
from app.main import create_app
from fastapi.testclient import TestClient


def test_env_file_is_application_relative_and_environment_wins(tmp_path, monkeypatch):
    assert ENV_FILE == PROJECT_ROOT / '.env'
    assert Settings.model_config['env_file'] == ENV_FILE
    configured = tmp_path / 'application.env'
    configured.write_text('LLM_PROVIDER=gemini\nLLM_MODEL=gemini-3.1-flash-lite\nGEMINI_API_KEY=fake-file-key\n')
    other = tmp_path / 'elsewhere'
    other.mkdir()
    (other / '.env').write_text('LLM_PROVIDER=openai\nGEMINI_API_KEY=wrong-file\n')
    monkeypatch.chdir(other)
    monkeypatch.setitem(Settings.model_config, 'env_file', configured)
    for name in ('LLM_PROVIDER', 'LLM_MODEL', 'GEMINI_API_KEY'):
        monkeypatch.delenv(name, raising=False)
    settings = Settings()
    assert settings.llm_provider == 'gemini'
    assert settings.gemini_api_key.get_secret_value() == 'fake-file-key'
    monkeypatch.setenv('LLM_MODEL', 'explicit-model')
    assert Settings().llm_model == 'explicit-model'


def test_runtime_health_reports_loaded_snapshot_not_edited_env(settings, monkeypatch):
    settings.llm_provider = 'gemini'
    settings.llm_model = 'gemini-3.1-flash-lite'
    settings.gemini_api_key = SecretStr('private-key')
    with TestClient(create_app(settings)) as client:
        monkeypatch.setenv('LLM_MODEL', 'different-after-startup')
        health = client.get('/api/health')
        assert health.json()['model'] == 'gemini-3.1-flash-lite'
        assert health.json()['provider'] == 'gemini'
        assert health.json()['api_key_present'] is True
        assert 'private-key' not in health.text


@pytest.mark.parametrize('payload', [
    {'error': {'status': 'INVALID_ARGUMENT', 'message': 'private-key private prompt',
               'details': [{'reason': 'API_KEY_INVALID', 'metadata': {'secret': 'private-key'}}]}},
    {'error': {'status': 'private-key', 'message': 'private prompt'}},
    {'error': {'status': [], 'details': None}}, [],
])
def test_diagnostics_log_safe_metadata_only(payload, caplog):
    token = request_path.set('/api/chat')
    try:
        log_http_failure('gemini', 'gemini-3.1-flash-lite', httpx.Response(400, json=payload))
    finally:
        request_path.reset(token)
    assert 'http_status=400' in caplog.text
    assert 'model=gemini-3.1-flash-lite' in caplog.text
    assert 'path=/api/chat' in caplog.text
    assert 'private' not in caplog.text


@pytest.mark.parametrize('status,message', [(404, 'model is unavailable'), (503, 'temporarily unavailable')])
def test_gemini_failure_has_actionable_message(settings, status, message, caplog):
    settings.gemini_api_key = SecretStr('private-key')
    async def run():
        async with httpx.AsyncClient(transport=httpx.MockTransport(
            lambda r: httpx.Response(status, json={'error': {'status': 'UNAVAILABLE', 'message': 'private'}}))) as client:
            with pytest.raises(TutorError) as caught:
                await GeminiProvider(settings, client).generate(instructions='', messages=[])
            assert message in caught.value.message
    asyncio.run(run())
    assert f'http_status={status}' in caplog.text
    assert 'private' not in caplog.text


def test_request_logs_use_route_template_without_query_or_ids(settings, caplog):
    class FailingProvider:
        async def generate(self, **kwargs):
            log_http_failure('gemini', 'gemini-3.1-flash-lite', httpx.Response(503))
            raise TutorError('provider_failure', 'Temporarily unavailable')
    with TestClient(create_app(settings, FailingProvider())) as client:
        session = client.post('/api/sessions').json()['session_id']
        response = client.post('/api/chat?secret=private-query', json={
            'session_id': session, 'message': 'private-prompt'})
        assert response.status_code == 502
    assert 'path=/api/chat ' in caplog.text
    assert 'private' not in caplog.text
    assert session not in caplog.text


def test_invalid_configuration_metadata_is_not_echoed(settings):
    settings.llm_provider = 'private-invalid-provider'
    assert provider_metadata(settings) == {'provider': 'unconfigured', 'model': None, 'api_key_present': False}
