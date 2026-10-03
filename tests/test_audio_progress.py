import json
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.audio_progress.service import event_key
from app.main import create_app
from tests.conftest import MockProvider
from tests.test_learning_memory import create, profile, observation
from tests.test_conversation import start, body, reply
from tests.test_speech import FakeSpeech, upload, speech_client
from tests.test_postgres import pg_settings
from tests.test_staging import gated, login


@pytest.fixture(params=['sqlite', 'postgres'])
def storage_settings(request, settings):
    return settings if request.param == 'sqlite' else request.getfixturevalue('pg_settings')


def base(learner):
    return f'/api/learners/{learner}/audio'


def attempt(client, learner, exercise='n5-place', key=None):
    key = key or str(uuid4())
    result = client.post(base(learner) + '/attempts', json={'attempt_id': key, 'exercise_id': exercise})
    assert result.status_code == 201, result.text
    return key


def complete(client, learner, key, **answer):
    return client.post(base(learner) + f'/attempts/{key}/complete', json=answer)


def progress(client, learner):
    result = client.get(base(learner) + '/progress')
    assert result.status_code == 200, result.text
    return result.json()


def test_listening_accuracy_assistance_replay_restart(storage_settings):
    provider = MockProvider()
    with TestClient(create_app(storage_settings, provider)) as client:
        learner = create(client)
        before = profile(client, learner)
        from app.audio_progress.service import CATALOG
        exercise = CATALOG['listening'][0]
        key = attempt(client, learner, exercise['id'])
        assert progress(client, learner)['listening']['unassisted']['completed'] == 0
        result = complete(client, learner, key, choice=exercise['answer'])
        assert result.json()['correct'] is True
        assert complete(client, learner, key, choice=exercise['answer']).json() == result.json()
        assert complete(client, learner, key, choice=(exercise['answer']+1)%3).status_code == 409
        wrong = attempt(client, learner, exercise['id'])
        assert complete(client, learner, wrong, choice=(exercise['answer']+1)%3).json()['correct'] is False
        assisted = attempt(client, learner, exercise['id'])
        assert complete(client, learner, assisted, choice=exercise['answer'], assisted=True).status_code == 200
        data = progress(client, learner)
        assert data['listening'] == {'attempts': 3, 'unassisted': {'completed': 2, 'correct': 1, 'accuracy': 50}, 'assisted': {'completed': 1, 'correct': 1, 'accuracy': 100}}
        assert progress(client, learner) == data
        assert profile(client, learner)['skills'] == before['skills']
        assert not provider.calls
    with TestClient(create_app(storage_settings, provider)) as restarted:
        assert progress(restarted, learner) == data


@pytest.mark.parametrize('mode', ['read', 'answer', 'repeat'])
def test_speaking_requires_success_receipt_no_transcript_or_score(speech_client, mode):
    client, fake, learner = speech_client
    from app.audio_progress.service import CATALOG
    exercise = next(e for e in CATALOG['speaking'] if e['mode'] == mode)
    key = attempt(client, learner, exercise['id'])
    unknown = str(uuid4())
    assert complete(client, learner, key, transcription_id=unknown).status_code == 422
    fake.error = Exception('offline failure')
    assert upload(client, learner, request_id=unknown).status_code >= 500
    assert progress(client, learner)['speaking'][mode] == {'attempts': 1, 'completed': 0}
    fake.error = None
    receipt = upload(client, learner).json()['request_id']
    assert progress(client, learner)['speaking'][mode]['completed'] == 0
    assert complete(client, learner, key, transcription_id=receipt).status_code == 200
    assert complete(client, learner, key, transcription_id=receipt).status_code == 200
    assert progress(client, learner)['speaking'][mode] == {'attempts': 1, 'completed': 1}
    other = attempt(client, learner, exercise['id'])
    assert complete(client, learner, other, transcription_id=receipt).status_code == 409
    with client.app.state.repository.connection() as db:
        rows = db.execute("SELECT score,metadata_json FROM learning_events WHERE learner_id=? AND source=?", (learner, 'speaking_'+mode)).fetchall()
        assert all(score is None and fake.text not in metadata for score, metadata in rows)


def test_voice_mixed_finish_replay_atomic_evidence(storage_settings):
    provider = MockProvider(reply(observations=[observation(1)]))
    storage_settings.groq_api_key = SecretStr('offline-placeholder')
    with TestClient(create_app(storage_settings, provider, FakeSpeech())) as client:
        learner = create(client)
        state = start(client, learner).json()
        assert client.post('/api/chat', json=body(learner, state)).status_code == 200
        finish = f'/api/learners/{learner}/conversations/{state["session_id"]}/finish'
        assert client.post(finish).status_code == 200
        assert progress(client, learner)['voice']['completed_conversations'] == 0
        state = start(client, learner).json()
        receipt = upload(client, learner).json()['request_id']
        request = body(learner, state, transcription_id=receipt)
        response = client.post('/api/chat', json=request)
        assert response.status_code == 200, response.text
        assert client.post('/api/chat', json=request).json() == response.json()
        assert client.post('/api/chat', json=body(learner, state, transcription_id=receipt)).status_code == 409
        assert client.post('/api/chat', json=body(learner, state, message='水をください。')).status_code == 200
        finish = f'/api/learners/{learner}/conversations/{state["session_id"]}/finish'
        assert client.post(finish).status_code == 200
        first = progress(client, learner)
        assert first['voice'] == {'completed_conversations': 1, 'confirmed_turns': 1}
        assert client.post(finish).status_code == 200
        assert client.post('/api/chat', json=request).json() == response.json()
        assert progress(client, learner) == first
        with client.app.state.repository.connection() as db:
            assert db.execute('SELECT COUNT(*) FROM conversation_turns WHERE session_id=?', (state['session_id'],)).fetchone()[0] == 2
            assert db.execute("SELECT COUNT(*) FROM learning_events WHERE session_id=? AND event_type='performance'", (state['session_id'],)).fetchone()[0] == 2
    with TestClient(create_app(storage_settings, provider)) as client:
        assert progress(client, learner) == first


def test_attempt_ownership_validation_and_concurrent_completion(client):
    learner, other = create(client), create(client)
    from app.audio_progress.service import CATALOG
    exercise = CATALOG['listening'][0]
    key = attempt(client, learner, exercise['id'])
    assert complete(client, other, key, choice=0).status_code == 404
    assert client.post(base(other)+'/attempts', json={'attempt_id': key, 'exercise_id': exercise['id']}).status_code == 409
    assert complete(client, learner, key, choice=True).status_code == 422
    assert complete(client, learner, key, choice=0, accuracy=100).status_code == 422
    with ThreadPoolExecutor(2) as pool:
        assert all(r.status_code == 200 for r in pool.map(lambda _: complete(client, learner, key, choice=0), range(2)))
    assert progress(client, learner)['listening']['unassisted']['completed'] == 1


def test_staging_audio_ownership(gated):
    login(gated)
    learner = create(gated)
    key = attempt(gated, learner)
    gated.cookies.clear()
    assert gated.get(base(learner)+'/progress').status_code == 401
    login(gated)
    assert gated.get(base(learner)+'/progress').status_code == 404
    assert complete(gated, learner, key, choice=0).status_code == 404


def test_speaking_restart_and_cross_activity_receipt_reuse(storage_settings):
    storage_settings.groq_api_key = SecretStr('offline-placeholder')
    provider = MockProvider(reply())
    with TestClient(create_app(storage_settings, provider, FakeSpeech())) as client:
        learner = create(client)
        key = attempt(client, learner, 'beginner-read-hello')
        receipt = upload(client, learner).json()['request_id']
        assert complete(client, learner, key, transcription_id=receipt).status_code == 200
        state = start(client, learner).json()
        # Even matching client UUIDs cannot reuse a speaking receipt as a voice turn.
        request = body(learner, state, transcription_id=receipt)
        request['request_id'] = key
        assert client.post('/api/chat', json=request).status_code == 409
        assert not provider.calls
        data = progress(client, learner)
        with client.app.state.repository.connection() as db:
            assert db.execute('SELECT COUNT(*) FROM conversation_turns').fetchone()[0] == 0
    with TestClient(create_app(storage_settings, provider)) as client:
        assert progress(client, learner) == data
        assert complete(client, learner, key, transcription_id=receipt).status_code == 200


def test_voice_provider_failure_has_no_activity_then_safe_retry(speech_client, provider):
    client, _, learner = speech_client
    state = start(client, learner).json()
    receipt = upload(client, learner).json()['request_id']
    request = body(learner, state, transcription_id=receipt)
    from app.errors import TutorError
    provider.error = TutorError('provider_unavailable', 'Offline fixture failure.', 503)
    assert client.post('/api/chat', json=request).status_code == 503
    assert progress(client, learner)['voice'] == {'completed_conversations': 0, 'confirmed_turns': 0}
    provider.error = None
    provider.raw = reply()
    assert client.post('/api/chat', json=request).status_code == 200
    assert client.post('/api/chat', json=request).status_code == 200
    assert progress(client, learner)['voice']['confirmed_turns'] == 1


def test_legacy_text_fingerprint_is_preserved():
    from app.tutor.schemas import ChatRequest
    from app.learner.sessions import request_fingerprint
    import hashlib
    request = ChatRequest(session_id=uuid4(), learner_id=uuid4(), request_id=uuid4(), message='こんにちは。')
    old = request.model_dump_json(exclude={'request_id', 'transcription_id'})
    assert request_fingerprint(request) == hashlib.sha256(old.encode()).hexdigest()


def test_v7_index_migration_preserves_all_rows_and_rolls_back(storage_settings, monkeypatch):
    from app.audio_progress import migrations
    from app.assessment.questions import QuestionBank
    original = migrations.migrate
    monkeypatch.setattr(migrations, 'migrate', lambda db: None)
    with TestClient(create_app(storage_settings, MockProvider())) as client:
        learner = create(client)
        start(client, learner)
        repo = client.app.state.repository
        tables = ['learner_state', 'skill_state', 'learning_events', 'tutor_sessions', 'conversation_states', 'jlpt_sessions', 'review_schedules']
        with repo.connection() as db:
            assert db.execute('PRAGMA user_version').fetchone()[0] == 7
            before = {t: db.execute(f'SELECT * FROM {t}').fetchall() for t in tables}
    def fail(db):
        original(db)
        raise ValueError('offline migration failure')
    monkeypatch.setattr(migrations, 'migrate', fail)
    from app.errors import TutorError
    with pytest.raises(TutorError):
        repo.initialize(QuestionBank.load())
    with repo.connection() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 7
    monkeypatch.setattr(migrations, 'migrate', original)
    for _ in range(2):
        repo.initialize(QuestionBank.load())
        with repo.connection() as db:
            assert db.execute('PRAGMA user_version').fetchone()[0] == 8
            assert {t: db.execute(f'SELECT * FROM {t}').fetchall() for t in tables} == before
