import json
import httpx

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.config import Settings
from app.main import create_app


@pytest.fixture(autouse=True)
def offline_only(monkeypatch):
    """Fail closed if a test accidentally attempts an external API connection."""
    def blocked(*args, **kwargs):
        raise AssertionError('Tests are offline: inject a fake provider or MockTransport')
    async def blocked_async(*args, **kwargs):
        blocked()
    monkeypatch.setattr(httpx.HTTPTransport, 'handle_request', blocked)
    monkeypatch.setattr(httpx.AsyncHTTPTransport, 'handle_async_request', blocked_async)


def sample_response():
    return {
        'message': 'Use に for the destination.',
        'evaluation': {'status': 'understandable_but_incorrect', 'correct': False, 'natural': False},
        'correction': {'original': '日本を行きたいです。', 'improved': '日本に行きたいです。'},
        'explanation': 'Place + に + 行く. に marks the destination of 行く.',
        'examples': ['学校に行きます。', '東京に行きたいです。'],
        'detected_topics': ['particle_ni', 'verb_iku'],
        'exercise': None,
    }


class MockProvider:
    def __init__(self, raw=None):
        self.raw = raw if raw is not None else json.dumps(sample_response(), ensure_ascii=False)
        self.calls = []
        self.error = None

    async def generate(self, **kwargs):
        self.calls.append(kwargs)
        if self.error:
            raise self.error
        return self.raw


@pytest.fixture
def settings(tmp_path):
    return Settings(_env_file=None, openai_api_key=SecretStr(''), gemini_api_key=SecretStr(''),
                    llm_provider='openai', llm_model='',
                    max_history_turns=2, max_sessions=10, session_ttl_seconds=60,
                    assessment_db_path=str(tmp_path / 'assessment.sqlite3'))


@pytest.fixture
def provider():
    return MockProvider()


@pytest.fixture
def client(settings, provider):
    with TestClient(create_app(settings, provider), raise_server_exceptions=False) as test_client:
        yield test_client


@pytest.fixture
def session(client):
    response = client.post('/api/sessions')
    assert response.status_code == 201
    return response.json()['session_id']
