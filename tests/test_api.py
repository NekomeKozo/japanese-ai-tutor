import json
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.errors import TutorError
from app.main import create_app
from tests.conftest import sample_response


def test_frontend_and_health(client):
    assert client.get('/').status_code == 200
    assert 'AI Japanese Tutor' in client.get('/').text
    assert client.get('/static/app.js').status_code == 200
    assert client.get('/static/styles.css').status_code == 200
    assert client.get('/api/health').json()['provider_configured'] is False
    assert client.get('/').headers['cache-control'] == 'no-store'
    assert client.get('/openapi.json').status_code == 200


def test_chat_correction(client, session):
    response = client.post('/api/chat', json={'session_id': session, 'message': '日本を行きたいです。', 'mode': 'correct'})
    assert response.status_code == 200
    assert response.json()['response']['correction']['improved'] == '日本に行きたいです。'
    assert response.json()['session_id'] == session


@pytest.mark.parametrize('message', ['', ' \n\t ', 'x' * 4001, None, 123])
def test_invalid_message(client, session, provider, message):
    response = client.post('/api/chat', json={'session_id': session, 'message': message})
    assert response.status_code == 422
    assert response.json()['error']['code'] == 'invalid_request'
    assert not provider.calls


@pytest.mark.parametrize('extra', [{'mode': 'voice'}, {'level': 'N0'}, {'secret': 'unexpected'}])
def test_invalid_options(client, session, extra):
    assert client.post('/api/chat', json={'session_id': session, 'message': 'hello', **extra}).status_code == 422


def test_malformed_request_body(client):
    response = client.post('/api/chat', content='{broken', headers={'Content-Type': 'application/json'})
    assert response.status_code == 422


def test_unknown_session(client, provider):
    response = client.post('/api/chat', json={'session_id': str(uuid4()), 'message': 'hello'})
    assert response.status_code == 404
    assert not provider.calls


def test_history_isolated_and_bounded(client, session, provider):
    for i in range(4):
        assert client.post('/api/chat', json={'session_id': session, 'message': f'Japanese question {i}'}).status_code == 200
    assert [len(call['messages']) for call in provider.calls] == [1, 3, 5, 5]
    latest = provider.calls[-1]['messages']
    assert 'question 1' in latest[0].content
    assert latest[1].role == 'assistant'
    assert json.loads(latest[1].content)['correction']['improved'] == '日本に行きたいです。'
    second = client.post('/api/sessions').json()['session_id']
    client.post('/api/chat', json={'session_id': second, 'message': 'another learner'})
    assert len(provider.calls[-1]['messages']) == 1


def test_delete_session(client, session):
    assert client.delete(f'/api/sessions/{session}').status_code == 204
    assert client.post('/api/chat', json={'session_id': session, 'message': 'hello'}).status_code == 404


@pytest.mark.parametrize('raw', ['not json', '[]', '{}', '```json\n{}\n```', '{"message": "hello"}', 'x' * 24001])
def test_invalid_response_does_not_save_turn(client, session, provider, raw):
    provider.raw = raw
    result = client.post('/api/chat', json={'session_id': session, 'message': 'bad turn'})
    assert result.status_code == 502
    assert result.json()['error']['code'] == 'invalid_model_response'
    provider.raw = json.dumps(sample_response())
    assert client.post('/api/chat', json={'session_id': session, 'message': 'retry'}).status_code == 200
    assert len(provider.calls[-1]['messages']) == 1


@pytest.mark.parametrize('mode', ['chat', 'correct', 'grammar', 'vocabulary', 'examples', 'exercise', 'quiz'])
def test_all_modes(client, session, provider, mode):
    result = client.post('/api/chat', json={'session_id': session, 'message': '〜たい', 'mode': mode, 'level': 'N4'})
    assert result.status_code == 200
    assert 'Learner-selected level: N4' in provider.calls[-1]['instructions']
    assert 'Do not use romaji' in provider.calls[-1]['instructions']
    assert 'Learning task:' in provider.calls[-1]['messages'][-1].content


def test_exercise_roundtrip(client, session, provider):
    payload = sample_response()
    payload.update(message='Let’s practice.', evaluation=None, correction=None, explanation=None, examples=[],
                   exercise={'kind': 'quiz', 'question': 'Japan is the destination. Which particle fits: 日本＿行きます。',
                             'hint': 'Think of the destination marker.', 'choices': ['を', 'に', 'で']})
    provider.raw = json.dumps(payload)
    first = client.post('/api/chat', json={'session_id': session, 'message': 'particles', 'mode': 'quiz'})
    assert first.json()['response']['exercise']['choices'] == ['を', 'に', 'で']
    client.post('/api/chat', json={'session_id': session, 'message': 'に'})
    assert '日本' in provider.calls[-1]['messages'][1].content


def test_safe_provider_error(client, session, provider):
    provider.error = TutorError('provider_timeout', 'Please try again.', 504)
    result = client.post('/api/chat', json={'session_id': session, 'message': 'hello'})
    assert result.status_code == 504
    provider.error = None
    assert client.post('/api/chat', json={'session_id': session, 'message': 'retry'}).status_code == 200
    assert len(provider.calls[-1]['messages']) == 1


def test_unexpected_exception_does_not_leak(client, session, provider):
    provider.error = RuntimeError('SECRET_UPSTREAM_BODY')
    response = client.post('/api/chat', json={'session_id': session, 'message': 'hello'})
    assert response.status_code == 500
    assert 'SECRET' not in response.text
    provider.error = None
    assert client.post('/api/chat', json={'session_id': session, 'message': 'retry'}).status_code == 200


def test_missing_key_still_allows_startup(settings):
    with TestClient(create_app(settings)) as client:
        session = client.post('/api/sessions').json()['session_id']
        result = client.post('/api/chat', json={'session_id': session, 'message': 'hello'})
        assert result.status_code == 503
        assert result.json()['error']['code'] == 'missing_api_key'


def test_unknown_provider(settings):
    settings.llm_provider = 'not_implemented'
    with TestClient(create_app(settings)) as client:
        assert not client.get('/api/health').json()['provider_configured']
        session = client.post('/api/sessions').json()['session_id']
        assert client.post('/api/chat', json={'session_id': session, 'message': 'hello'}).status_code == 503
