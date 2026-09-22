import json
import sqlite3
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.errors import TutorError
from app.learner.catalog import TOPICS
from app.learner.context import MAX_CONTEXT_BYTES, build_context
from app.learner.schemas import LearningEvent
from app.learner.sessions import MAX_HISTORY_CHARS
from app.main import create_app
from tests.conftest import sample_response
from tests.test_assessment import skip, start


def create(client):
    response = client.post('/api/learners')
    assert response.status_code == 201
    return response.json()['learner_id']


def profile(client, learner):
    response = client.get(f'/api/learners/{learner}/profile')
    assert response.status_code == 200
    return response.json()


def record(client, learner, score, topic='particle_ni', event_id=None, skill='grammar', **kwargs):
    event = LearningEvent(event_id=event_id or uuid4(), learner_id=learner, event_type='performance',
        topic_key=topic, skill=skill, score=score, source='manual_review', **kwargs)
    return client.app.state.learners.record(event)


def observation(score=0, **kwargs):
    return {'event_type': 'performance', 'skill': 'grammar', 'topic_key': 'particle_ni',
            'score': score, 'difficulty': 2, 'error_tags': ['destination_particle'], **kwargs}


def saved_request(client, learner):
    session = client.post(f'/api/learners/{learner}/sessions')
    assert session.status_code == 201
    return {'learner_id': learner, 'session_id': session.json()['session_id'],
            'request_id': str(uuid4()), 'message': '日本を行きたいです。'}


def test_default_profile_has_no_fabricated_scores(client):
    learner = create(client)
    data = profile(client, learner)
    assert data['profile_source'] == 'default' and data['estimated_level'] == 'Beginner'
    assert data['initial_placement'] is None and data['overall_score'] is None
    assert all(s['estimate'] is None for s in data['skills'].values())
    assert data['weak_topics'] == [] and data['common_mistakes'] == []
    assert data['created_at'].endswith('+00:00')


def test_placement_automatically_initializes_and_survives_restart(settings, provider):
    with TestClient(create_app(settings, provider)) as client:
        state = start(client)
        for _ in range(4): state = skip(client, state).json()
        learner = state['learner_id']
        original = state['result']
        data = profile(client, learner)
        assert data['profile_source'] == 'placement_assessment'
        assert data['initial_placement'] == original
        assert data['skills']['hiragana']['placement_evidence'] == 2
    with TestClient(create_app(settings, provider)) as client:
        assert profile(client, learner)['initial_placement'] == original


def test_preferences_persist_and_are_validated(settings, provider):
    with TestClient(create_app(settings, provider)) as client:
        learner = create(client)
        changes = {'romaji_enabled': True, 'explanation_language': 'japanese', 'correction_style': 'gentle',
                   'furigana_enabled': False, 'preferred_difficulty': 'N4', 'primary_goal': 'travel'}
        assert client.patch(f'/api/learners/{learner}/preferences', json=changes).status_code == 200
        assert client.patch(f'/api/learners/{learner}/preferences', json={'romaji_enabled': 'yes'}).status_code == 422
        assert client.patch(f'/api/learners/{learner}/preferences', json={'estimated_level': 'N1'}).status_code == 422
        assert client.patch(f'/api/learners/{learner}/preferences', json={'correction_style': None}).status_code == 422
    with TestClient(create_app(settings, provider)) as client:
        assert all(profile(client, learner)['preferences'][key] == value for key,value in changes.items())


def test_weakness_requires_repeated_evidence_then_recovers(client):
    learner = create(client)
    record(client, learner, 0)
    assert not profile(client, learner)['weak_topics']
    record(client, learner, .25, topic='destination_particle_ni')
    record(client, learner, 0, topic='particle_ni_destination')
    data = profile(client, learner)
    assert len(data['weak_topics']) == 1
    assert data['weak_topics'][0]['topic_key'] == 'particle_ni_destination'
    assert len(data['common_mistakes']) == 1 and data['common_mistakes'][0]['occurrences'] == 3
    assert data['common_mistakes'][0]['status'] == 'active'
    for _ in range(8): record(client, learner, 1)
    data = profile(client, learner)
    assert not data['weak_topics'] and data['strong_topics'][0]['topic_key'] == 'particle_ni_destination'
    assert data['common_mistakes'][0]['status'] == 'improving'
    assert data['skills']['grammar']['recent_average'] == 1
    assert data['skills']['grammar']['recent_count'] == 8
    assert data['last_activity_at'] and data['updated_at'].endswith('+00:00')


@pytest.mark.parametrize('topic,skill,kind', [('vocab_taberu','vocabulary','vocabulary'),
    ('tai_form','grammar','grammar'), ('kanji_gaku_reading','kanji','kanji'), ('kanji_gaku_meaning','kanji','kanji')])
def test_topic_exposure_success_and_failure(client, topic, skill, kind):
    learner = create(client)
    record(client, learner, 1, topic=topic, skill=skill)
    record(client, learner, 0, topic=topic, skill=skill)
    item = profile(client, learner)['topic_memory'][0]
    assert item['topic_type'] == kind and item['encounters'] == 2
    assert item['correct_count'] == item['incorrect_count'] == 1
    assert item['last_correct_at'] and item['recent_score'] == .5


def test_explanations_are_not_proficiency_evidence(client):
    learner = create(client)
    event = LearningEvent(event_id=uuid4(), learner_id=learner, event_type='concept_explained',
                         topic_key='tai_form', skill='grammar', source='tutor_chat')
    client.app.state.learners.record(event)
    data = profile(client, learner)
    assert data['topic_memory'][0]['encounters'] == 1
    assert data['topic_memory'][0]['recent_score'] is None
    assert data['skills']['grammar']['learning_count'] == 0


def test_duplicate_and_conflicting_event_ids(client):
    learner = create(client)
    event_id = uuid4()
    assert record(client, learner, 0, event_id=event_id)
    assert not record(client, learner, 0, event_id=event_id)
    assert profile(client, learner)['topic_memory'][0]['encounters'] == 1
    with pytest.raises(TutorError): record(client, learner, 1, event_id=event_id)


def test_unknown_tags_are_bounded_unscored_exposures(client):
    learner = create(client)
    for i in range(12): record(client, learner, 0, topic=f'invented_{i}')
    data = profile(client, learner)
    assert len(data['topic_memory']) == 1 and data['topic_memory'][0]['topic_key'] == 'other_grammar'
    assert not data['weak_topics'] and not data['common_mistakes']
    assert data['skills']['grammar']['learning_count'] == 0


def test_transaction_rolls_back_event_and_state(client):
    learner = create(client)
    repository = client.app.state.learners.repository
    with repository.connection() as db:
        db.execute("CREATE TRIGGER fail_topic BEFORE INSERT ON learner_topics BEGIN SELECT RAISE(ABORT,'test'); END")
    with pytest.raises(TutorError): record(client, learner, 0)
    assert profile(client, learner)['topic_memory'] == []
    with repository.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM learning_events WHERE learner_id=?', (learner,)).fetchone()[0] == 0


def test_compact_context_no_history_dump(client):
    learner = create(client)
    for topic in TOPICS:
        for _ in range(4): record(client, learner, 0, topic=topic)
    data = profile(client, learner)
    context = build_context(data)
    assert len(context.encode('utf-8')) <= MAX_CONTEXT_BYTES
    parsed = json.loads(context)
    assert len(parsed['weak_topics']) <= 5 and len(parsed['repeated_mistakes']) <= 5
    assert len(parsed['strong_topics']) <= 3 and len(parsed['recent_topics']) <= 5
    assert 'event_id' not in context and 'initial_placement' not in context and 'created_at' not in context


def test_persistent_chat_records_observations_and_retry_once(client, provider):
    learner = create(client)
    provider.raw = json.dumps({**sample_response(), 'learning_observations': [observation(), observation()]})
    body = saved_request(client, learner)
    first = client.post('/api/chat', json=body)
    second = client.post('/api/chat', json=body)
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() and len(provider.calls) == 1
    data = profile(client, learner)
    assert data['topic_memory'][0]['encounters'] == 1
    assert data['skills']['grammar']['learning_count'] == 1
    assert client.post('/api/chat', json={**body, 'message': 'different'}).status_code == 409
    saved = client.get(f'/api/learners/{learner}/sessions/{body["session_id"]}').json()
    assert saved['interaction_count'] == 1 and len(saved['turns']) == 1
    assert 'learning_observations' not in saved['turns'][0]['response']


@pytest.mark.parametrize('observations', [None, 'bad', [{'bad': True}], [observation(score=4)],
    [observation(event_type='concept_explained',score=1)], [observation(error_tags=['x']*6)]])
def test_malformed_observations_do_not_discard_reply(client, provider, observations):
    learner = create(client)
    provider.raw = json.dumps({**sample_response(), 'learning_observations': observations})
    body = saved_request(client, learner)
    assert client.post('/api/chat', json=body).status_code == 200
    assert profile(client, learner)['topic_memory'] == []


def test_learners_and_sessions_are_isolated(client, provider):
    a, b = create(client), create(client)
    record(client, a, 0)
    body = saved_request(client, a)
    assert client.post('/api/chat', json=body).status_code == 200
    calls = len(provider.calls)
    assert client.post('/api/chat', json={**body, 'learner_id': b, 'request_id': str(uuid4())}).status_code == 404
    assert len(provider.calls) == calls
    assert client.get(f'/api/learners/{b}/sessions/{body["session_id"]}').status_code == 404
    assert client.post(f'/api/learners/{b}/sessions/{body["session_id"]}/close').status_code == 404
    assert profile(client, b)['topic_memory'] == []
    assert client.get(f'/api/learners/{b}/sessions').json() == []


def test_saved_conversation_survives_restart(settings, provider):
    with TestClient(create_app(settings, provider)) as client:
        learner = create(client)
        body = saved_request(client, learner)
        assert client.post('/api/chat', json=body).status_code == 200
    with TestClient(create_app(settings, provider)) as client:
        assert client.get(f'/api/learners/{learner}/sessions/{body["session_id"]}').json()['interaction_count'] == 1
        assert client.post('/api/chat', json={**body, 'request_id': str(uuid4()), 'message': 'Explain more'}).status_code == 200
        assert len(provider.calls[-1]['messages']) == 3
        assert '日本を行きたいです。' in provider.calls[-1]['messages'][0].content


def test_context_preferences_reach_tutor(client, provider):
    learner = create(client)
    for _ in range(3): record(client, learner, 0)
    client.patch(f'/api/learners/{learner}/preferences', json={
        'romaji_enabled':True,'explanation_language':'japanese','correction_style':'gentle','preferred_difficulty':'N4'})
    assert client.post('/api/chat', json=saved_request(client, learner)).status_code == 200
    instructions = provider.calls[-1]['instructions']
    assert 'Learner-selected level: N4' in instructions
    assert 'Use romaji sparingly' in instructions and 'Do not use romaji' not in instructions
    assert 'Explain in japanese' in instructions and 'gentle correction style' in instructions
    assert 'Destination particle に' in instructions


def test_skill_updates_are_small_and_placement_unchanged(client):
    learner = create(client)
    repository = client.app.state.learners.repository
    with repository.connection() as db:
        db.execute("UPDATE skill_state SET baseline=3,estimate=3,placement_evidence=4 WHERE learner_id=? AND skill='grammar'", (learner,))
    record(client, learner, 0)
    assert profile(client, learner)['skills']['grammar']['estimate'] == 3
    for _ in range(4): record(client, learner, 0)
    data = profile(client, learner)
    assert data['skills']['grammar']['estimate'] == 2.85
    assert data['estimated_level'] == 'Beginner' and data['overall_score'] is None
    with repository.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM skill_history WHERE learner_id=?', (learner,)).fetchone()[0] == 1


def test_transcript_and_memory_rollback_together(client, provider):
    learner = create(client)
    body = saved_request(client, learner)
    provider.raw = json.dumps({**sample_response(), 'learning_observations': [observation()]})
    with client.app.state.learners.repository.connection() as db:
        db.execute("CREATE TRIGGER fail_topic BEFORE INSERT ON learner_topics BEGIN SELECT RAISE(ABORT,'test'); END")
    assert client.post('/api/chat', json=body).status_code == 503
    saved = client.get(f'/api/learners/{learner}/sessions/{body["session_id"]}').json()
    assert saved['turns'] == [] and saved['interaction_count'] == 0


def test_close_and_request_id_required(client):
    learner = create(client)
    body = saved_request(client, learner)
    no_id = {k:v for k,v in body.items() if k != 'request_id'}
    assert client.post('/api/chat', json=no_id).status_code == 422
    assert client.post(f'/api/learners/{learner}/sessions/{body["session_id"]}/close').status_code == 200
    assert client.post('/api/chat', json=body).status_code == 409


def test_history_has_hard_character_budget(client, provider):
    learner = create(client)
    body = saved_request(client, learner)
    for _ in range(8):
        assert client.post('/api/chat', json={**body,'request_id':str(uuid4()),'message':'日'*4000}).status_code == 200
    previous = provider.calls[-1]['messages'][:-1]
    assert sum(len(m.content) for m in previous) <= MAX_HISTORY_CHARS
    assert len(previous) % 2 == 0 and len(previous) < 14


def test_invalid_profile_and_pagination(client):
    assert client.get(f'/api/learners/{uuid4()}/profile').status_code == 404
    learner = create(client)
    assert client.get(f'/api/learners/{learner}/activity?limit=10000').status_code == 422
    assert client.get(f'/api/learners/{learner}/sessions?limit=10000').status_code == 422


def make_version_one(settings, provider):
    """Produce the exact Phase 2 four-table layout, including completed and active data."""
    with TestClient(create_app(settings, provider)) as client:
        completed = start(client)
        for _ in range(4): completed = skip(client, completed).json()
        active = start(client)
    with sqlite3.connect(settings.assessment_db_path) as db:
        for table in ('study_activities', 'study_sessions', 'conversation_turns', 'tutor_sessions', 'learning_events', 'mistake_state',
                      'learner_topics', 'skill_history', 'skill_state', 'learner_state', 'learning_topics'):
            db.execute(f'DROP TABLE {table}')
        db.execute('PRAGMA user_version=1')
        original = {table: db.execute(f'SELECT * FROM {table} ORDER BY 1,2').fetchall()
                    for table in ('assessments', 'assessment_answers', 'learner_profiles', 'assessment_questions')}
    return completed, active, original


def test_version_one_migration_preserves_all_old_rows_and_is_idempotent(settings, provider):
    completed, active, original = make_version_one(settings, provider)
    for _ in range(2):
        with TestClient(create_app(settings, provider)) as client:
            data = profile(client, completed['learner_id'])
            assert data['initial_placement'] == completed['result']
            assert client.get(f'/api/assessments/{active["assessment_id"]}').json() == active
            with sqlite3.connect(settings.assessment_db_path) as db:
                assert db.execute('PRAGMA user_version').fetchone()[0] == 5
                for table, rows in original.items():
                    assert db.execute(f'SELECT * FROM {table} ORDER BY 1,2').fetchall() == rows
                assert db.execute("SELECT COUNT(*) FROM learning_events WHERE event_type='assessment_completed'").fetchone()[0] == 1


def test_failed_migration_rolls_back_schema_and_preserves_version_one(settings, provider, monkeypatch):
    make_version_one(settings, provider)
    import app.learner.initialization as initialization
    def fail(*args): raise ValueError('test invalid migration input')
    monkeypatch.setattr(initialization, 'initialize_placement', fail)
    with TestClient(create_app(settings, provider)) as client:
        assert client.post('/api/learners').status_code == 503
        assert client.post('/api/sessions').status_code == 201
    with sqlite3.connect(settings.assessment_db_path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 1
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='learner_state'").fetchone()
        assert db.execute('SELECT COUNT(*) FROM learner_profiles').fetchone()[0] == 1


def test_developer_reset_requires_confirmation_and_is_scoped(client):
    from app.learner.reset import reset_learner
    state = start(client)
    for _ in range(4): state = skip(client, state).json()
    a, b = state['learner_id'], create(client)
    record(client, a, 0); record(client, b, 0)
    body = saved_request(client, a)
    client.post('/api/chat', json=body)
    repository = client.app.state.learners.repository
    before = profile(client, a)
    with pytest.raises(ValueError): reset_learner(repository, a, b)
    assert profile(client, a) == before
    reset_learner(repository, a, a)
    data = profile(client, a)
    assert data['initial_placement'] == state['result']
    assert not any(t['topic_key'] == 'particle_ni_destination' for t in data['topic_memory'])
    assert len(profile(client, b)['topic_memory']) == 1
    assert client.get(f'/api/learners/{a}/sessions').json() == []


def test_stale_saved_session_writer_cannot_overwrite(client):
    from app.tutor.schemas import ChatRequest, TutorResponse
    learner = create(client)
    body = saved_request(client, learner)
    service = client.app.state.saved_sessions
    assert client.post('/api/chat', json=body).status_code == 200
    with pytest.raises(TutorError) as error:
        service.commit(ChatRequest.model_validate({**body,'request_id':str(uuid4())}), TutorResponse.model_validate(sample_response()), [], 0)
    assert error.value.status == 409
    assert service.get(UUID(learner), UUID(body['session_id']))['interaction_count'] == 1


def test_old_mistakes_not_reported_as_recent(client):
    learner = create(client)
    for _ in range(3): record(client, learner, 0)
    with client.app.state.learners.repository.connection() as db:
        db.execute("UPDATE mistake_state SET recent_json=?,last_seen_at=? WHERE learner_id=?", ('["2020-01-01T00:00:00+00:00"]','2020-01-01T00:00:00+00:00',learner))
    data = profile(client, learner)
    assert data['common_mistakes'][0]['recent_occurrences'] == 0
    assert data['common_mistakes'][0]['status'] == 'inactive'
    assert json.loads(build_context(data))['repeated_mistakes'] == []


def test_legacy_session_cannot_switch_to_another_learner(client, session):
    a, b = create(client), create(client)
    assert client.post('/api/chat', json={'session_id':session,'message':'hello','learner_id':a}).status_code == 200
    assert client.post('/api/chat', json={'session_id':session,'message':'hello','learner_id':b}).status_code == 409


def test_failed_provider_leaves_saved_session_usable(client, provider):
    learner = create(client)
    body = saved_request(client, learner)
    provider.error = TutorError('provider_unavailable','Test unavailable',503)
    assert client.post('/api/chat', json=body).status_code == 503
    saved = client.get(f'/api/learners/{learner}/sessions/{body["session_id"]}').json()
    assert saved['turns'] == [] and saved['interaction_count'] == 0
    provider.error = None
    assert client.post('/api/chat', json=body).status_code == 200


def test_many_observations_count_once_per_skill_per_turn(client, provider):
    learner = create(client)
    provider.raw = json.dumps({**sample_response(), 'learning_observations': [
        observation(topic_key=topic) for topic in ('particle_ni','particle_de','verb_past','tai_form')]})
    assert client.post('/api/chat', json=saved_request(client, learner)).status_code == 200
    data = profile(client, learner)
    assert len(data['topic_memory']) == 4
    assert data['skills']['grammar']['learning_count'] == 1


def test_skill_drift_is_capped_and_easy_success_does_not_raise_advanced_estimate(client):
    learner = create(client)
    with client.app.state.learners.repository.connection() as db:
        db.execute("UPDATE skill_state SET baseline=8,estimate=8,placement_evidence=4 WHERE learner_id=? AND skill='grammar'",(learner,))
    for _ in range(5): record(client, learner, 1)
    assert profile(client, learner)['skills']['grammar']['estimate'] == 8
    for _ in range(50): record(client, learner, 0)
    assert profile(client, learner)['skills']['grammar']['estimate'] == 7
