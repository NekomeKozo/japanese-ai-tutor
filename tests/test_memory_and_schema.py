import asyncio
import json

import pytest

from app.errors import TutorError
from app.memory.conversation import ConversationStore
from app.tutor.schemas import ChatRequest, TutorResponse
from app.tutor.service import TutorService, parse_response
from tests.conftest import sample_response


def test_expiry_and_capacity():
    now = [0]
    store = ConversationStore(max_sessions=1, max_turns=2, ttl=60, clock=lambda: now[0])
    key = store.create()
    with pytest.raises(TutorError) as caught:
        store.create()
    assert caught.value.code == 'session_capacity'
    now[0] = 61
    new_key = store.create()
    assert new_key != key
    with pytest.raises(TutorError) as caught:
        with store.use(key):
            pass
    assert caught.value.code == 'session_expired'


def test_active_session_is_not_evicted():
    now = [0]
    store = ConversationStore(max_sessions=1, max_turns=2, ttl=60, clock=lambda: now[0])
    key = store.create()
    with store.use(key):
        now[0] = 61
        with pytest.raises(TutorError) as caught:
            store.create()
        assert caught.value.code == 'session_capacity'
        with pytest.raises(TutorError) as caught:
            store.delete(key)
        assert caught.value.code == 'session_busy'
    with store.use(key):
        pass


def test_concurrent_turn_rejected(settings):
    async def run():
        entered, release = asyncio.Event(), asyncio.Event()

        class WaitingProvider:
            async def generate(self, **kwargs):
                entered.set()
                await release.wait()
                return json.dumps(sample_response())

        store = ConversationStore(max_sessions=2, max_turns=2, ttl=60)
        service = TutorService(WaitingProvider(), store, settings)
        request = ChatRequest(session_id=store.create(), message='hello')
        first = asyncio.create_task(service.chat(request))
        await entered.wait()
        try:
            with pytest.raises(TutorError) as caught:
                await service.chat(request)
            assert caught.value.code == 'session_busy'
        finally:
            release.set()
            await first
        assert len(store.sessions[request.session_id].messages) == 2
    asyncio.run(run())


def test_total_timeout_releases_session(settings):
    async def run():
        class WaitingProvider:
            async def generate(self, **kwargs):
                await asyncio.Event().wait()

        # Short deadline for this unit test only; normal configuration has a 1s minimum.
        settings.llm_timeout_seconds = 0.01
        store = ConversationStore(max_sessions=2, max_turns=2, ttl=60)
        key = store.create()
        with pytest.raises(TutorError) as caught:
            await TutorService(WaitingProvider(), store, settings).chat(ChatRequest(session_id=key, message='hello'))
        assert caught.value.code == 'provider_timeout'
        with store.use(key) as session:
            assert session.messages == []
    asyncio.run(run())


@pytest.mark.parametrize('mutation', [
    {'message': '   '}, {'evaluation': {'status': 'correct', 'correct': 'yes', 'natural': True}},
    {'examples': 'not a list'}, {'unexpected': 'extra field'}, {'exercise': {'question': 'missing fields'}},
])
def test_schema_rejects_invalid_fields(mutation):
    payload = sample_response()
    payload.update(mutation)
    with pytest.raises(TutorError):
        parse_response(json.dumps(payload))


def test_schema_has_required_keys_and_no_answer_key():
    schema = TutorResponse.model_json_schema()
    assert set(schema['required']) == set(schema['properties'])
    assert schema['additionalProperties'] is False
    assert 'answer' not in schema['$defs']['Exercise']['properties']
    assert parse_response(json.dumps(sample_response())).correction.improved == '日本に行きたいです。'
