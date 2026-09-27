import asyncio
import json

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.errors import TutorError
from app.llm.base import Message
from app.llm.factory import create_provider
from app.llm.failover import FailoverProvider
from app.llm.groq import GroqProvider
from app.tutor.schemas import TutorResponse
from tests.conftest import sample_response
from tests.conftest import MockProvider
from app.main import create_app


class Fake:
    def __init__(self, error=None):
        self.error, self.calls = error, 0
    async def generate(self, **kwargs):
        self.calls += 1
        if self.error:
            raise self.error
        return json.dumps(sample_response())


def run(provider):
    return asyncio.run(provider.generate(instructions='Japanese tutor', messages=[Message('user', '日本語')], schema=TutorResponse.model_json_schema()))


@pytest.mark.parametrize('error', [None, 'provider_rate_limit', 'provider_timeout', 'provider_unavailable', 'temporary'])
def test_bounded_fallback(error):
    exc = TutorError('provider_failure' if error == 'temporary' else error, 'safe', retryable_provider=error == 'temporary') if error else None
    primary, fallback = Fake(exc), Fake()
    assert TutorResponse.model_validate_json(run(FailoverProvider(primary, fallback, 2))).message
    assert primary.calls == 1 and fallback.calls == int(error is not None)


@pytest.mark.parametrize('code', ['provider_refusal', 'invalid_model_response', 'provider_auth', 'provider_failure', 'scope_rejected', 'rate_limit', 'assessment_storage', 'invalid_request'])
def test_ineligible_errors_never_fallback(code):
    primary, fallback = Fake(TutorError(code, 'safe')), Fake()
    with pytest.raises(TutorError):
        run(FailoverProvider(primary, fallback, 2))
    assert primary.calls == 1 and fallback.calls == 0


def test_both_fail_safely():
    primary, fallback = Fake(TutorError('provider_timeout', 'safe')), Fake(TutorError('provider_auth', 'safe'))
    with pytest.raises(TutorError, match='temporarily unavailable'):
        run(FailoverProvider(primary, fallback, 2))
    assert primary.calls == fallback.calls == 1


def test_primary_hang_reserves_time_for_fallback():
    class Slow(Fake):
        async def generate(self, **kwargs):
            self.calls += 1
            await asyncio.sleep(1)
    primary, fallback = Slow(), Fake()
    assert run(FailoverProvider(primary, fallback, .05))
    assert primary.calls == fallback.calls == 1


def test_failover_cannot_alternate_again_during_one_http_request():
    from app.llm.common import request_path
    primary, fallback = Fake(TutorError('provider_timeout', 'safe')), Fake()
    router = FailoverProvider(primary, fallback, 2)
    token = request_path.set({})
    try:
        assert run(router)
        with pytest.raises(TutorError):
            run(router)
        assert primary.calls == fallback.calls == 1
    finally:
        request_path.reset(token)


@pytest.mark.parametrize('enabled', [False, True])
def test_http_router_and_disabled(settings, enabled):
    settings.llm_provider = 'gemini'
    settings.gemini_api_key = SecretStr('fake-gemini')
    settings.groq_api_key = SecretStr('fake-groq')
    settings.groq_model = 'openai/gpt-oss-20b'
    settings.llm_failover_enabled = enabled
    called = []
    def handler(request):
        called.append(request.url.host)
        if request.url.host == 'generativelanguage.googleapis.com':
            return httpx.Response(429)
        body = json.loads(request.content)
        assert body['model'] == settings.groq_model
        assert body['max_completion_tokens'] == settings.llm_max_output_tokens
        assert body['response_format']['json_schema']['schema'] == TutorResponse.model_json_schema()
        return httpx.Response(200, json={'choices': [{'finish_reason': 'stop', 'message': {'content': json.dumps(sample_response())}}]})
    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
            return await create_provider(settings, client).generate(instructions='Japanese tutor', messages=[Message('user', '日本語')], schema=TutorResponse.model_json_schema())
    if enabled:
        assert TutorResponse.model_validate_json(asyncio.run(call())).message
        assert called == ['generativelanguage.googleapis.com', 'api.groq.com']
    else:
        with pytest.raises(TutorError):
            asyncio.run(call())
        assert len(called) == 1


@pytest.mark.parametrize('finish,content,code', [('content_filter', '{}', 'provider_refusal'), ('length', '{}', 'incomplete_response'), ('stop', 'not-json', 'invalid_model_response')])
def test_groq_invalid_and_refusal(settings, finish, content, code):
    settings.groq_api_key = SecretStr('fake-groq')
    settings.groq_model = 'openai/gpt-oss-20b'
    async def call():
        async with httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, json={'choices': [{'finish_reason': finish, 'message': {'content': content}}]}))) as client:
            return await GroqProvider(settings, client).generate(instructions='safe', messages=[], schema={})
    with pytest.raises(TutorError) as caught:
        asyncio.run(call())
    assert caught.value.code == code


def test_fallback_saved_chat_retry_commits_once(settings):
    from tests.test_learning_memory import create, saved_request, observation
    primary = Fake(TutorError('provider_rate_limit', 'safe'))
    fallback = MockProvider(json.dumps({**sample_response(), 'learning_observations': [observation()]}))
    router = FailoverProvider(primary, fallback, 2)
    with TestClient(create_app(settings, router)) as client:
        learner = create(client)
        body = saved_request(client, learner)
        first = client.post('/api/chat', json=body)
        assert first.status_code == 200, first.text
        with client.app.state.repository.connection() as db:
            before = {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0]
                      for table in ('learning_events', 'conversation_turns', 'mastery_evidence', 'mastery_history', 'review_attempts')}
        assert client.post('/api/chat', json=body).json() == first.json()
        with client.app.state.repository.connection() as db:
            after = {table: db.execute(f'SELECT count(*) FROM {table}').fetchone()[0] for table in before}
        assert before == after
        assert primary.calls == len(fallback.calls) == 1


def test_fallback_review_attempt_commits_once(settings, monkeypatch):
    from datetime import timedelta
    from uuid import uuid4
    from tests import test_reviews as reviews
    from tests.test_learning_memory import create
    from app.assessment.schemas import SemanticEvaluation
    primary = Fake(TutorError('provider_timeout', 'safe'))
    evaluation = {'score': 1, 'meaning_correct': True, 'grammar_correct': True,
                  'naturalness': 1.0, 'acceptable_alternative': True,
                  'feedback_internal': 'Correct meaning.', 'detected_errors': []}
    # Keep the fake response checked against the real evaluator contract.
    payload = SemanticEvaluation.model_validate(evaluation).model_dump_json()
    fallback = MockProvider(payload)
    with TestClient(create_app(settings, FailoverProvider(primary, fallback, 2))) as client:
        learner, clock = create(client), reviews.Clock()
        monkeypatch.setattr('app.learner.events.now_iso', lambda: clock.now().isoformat())
        client.app.state.reviews.clock = client.app.state.curriculum.reviews.clock = clock
        reviews.record(client, learner, 'vocab_taberu', 'meaning', score=0)
        clock.value += timedelta(hours=1)
        base, path, activity = reviews.start_review(client, learner)
        assert client.post(path + '/open').status_code == 200
        body = {'submission_id': str(uuid4()), 'answer': 'consume a meal'}
        first = client.post(path + '/complete', json=body)
        assert first.status_code == 200, first.text
        assert client.post(path + '/complete', json=body).json() == first.json()
        assert primary.calls == len(fallback.calls) == 1
        with client.app.state.repository.connection() as db:
            assert db.execute('SELECT count(*) FROM review_attempts').fetchone()[0] == 2
            assert db.execute('SELECT count(*) FROM mastery_evidence').fetchone()[0] == 2
