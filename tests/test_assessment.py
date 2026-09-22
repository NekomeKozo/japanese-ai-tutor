import asyncio
import json
import sqlite3
import time
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

from app.assessment.engine import AssessmentEngine, MAX_QUESTIONS, stopping_reason
from app.assessment.evaluator import AnswerEvaluator
from app.assessment.questions import QuestionBank
from app.assessment.repository import AssessmentRepository
from app.assessment.results import build_profile
from app.assessment.schemas import AnswerRequest, AssessmentState, Evaluation, Evidence, MAJORS, SCRIPTS, StartRequest
from app.assessment.scoring import all_estimates, estimate, overall_confidence
from app.assessment.selector import select_question
from app.errors import TutorError
from app.main import create_app
from tests.conftest import MockProvider
from tests.test_assessment_core import evidence


def start(client):
    response = client.post('/api/assessments', json={})
    assert response.status_code == 201
    return response.json()


def skip(client, state):
    return client.post(f'/api/assessments/{state["assessment_id"]}/answers', json={
        'question_id': state['question']['id'], 'submission_id': str(uuid4()), 'dont_know': True})


def test_start_and_no_answer_leakage(client):
    state = start(client)
    assert state['question_number'] == 1 and state['question']['skill'] == 'hiragana'
    assert set(state['question']) == {'id', 'skill', 'question_type', 'prompt', 'choices'}
    text = json.dumps(state)
    for hidden in ['difficulty', 'answers', 'evaluation', 'explanation', 'jlpt_reference']:
        assert hidden not in text
    assert client.get(f'/api/assessments/{state["assessment_id"]}').json() == state
    assert client.get(f'/api/assessments/{state["assessment_id"]}/result').status_code == 409
    assert client.get('/static/../app/assessment/data/questions.json').status_code == 404


def test_correct_answer_and_no_midtest_feedback(client, provider):
    state = start(client)
    question = client.app.state.assessment.load(UUID(state['assessment_id'])).current
    response = client.post(f'/api/assessments/{state["assessment_id"]}/answers', json={
        'question_id': question.id, 'answer': question.answers[0], 'submission_id': str(uuid4())})
    assert response.status_code == 200
    assert response.json()['questions_answered'] == 1
    assert response.json()['question']['id'] != question.id
    assert 'score' not in response.text and 'correct' not in response.text
    assert not provider.calls


def test_skip_and_beginner_completion_and_profile(client):
    state = start(client)
    for _ in range(4):
        response = skip(client, state)
        assert response.status_code == 200
        state = response.json()
    assert state['status'] == 'completed'
    result = state['result']
    assert result['overall_estimate'] == 'Absolute Beginner'
    assert result['stopping_reason'] == 'beginner_screen'
    assert result['skills']['vocabulary']['estimated_level'] == 'Not assessed'
    assert result['skills']['vocabulary']['evidence_count'] == 0
    assert result['listening'] is None and result['speaking'] is None
    assert result['confidence_label'] == 'Low'
    assert 'hiragana' in result['recommended_starting_point']
    assert client.get(f'/api/assessments/{state["assessment_id"]}/result').json() == result


def test_idempotent_answer_and_conflicts(client):
    state = start(client)
    path = f'/api/assessments/{state["assessment_id"]}/answers'
    payload = {'question_id': state['question']['id'], 'submission_id': str(uuid4()), 'dont_know': True}
    first = client.post(path, json=payload)
    second = client.post(path, json=payload)
    assert first.status_code == second.status_code == 200
    assert second.json()['replayed'] is True
    assert second.json()['questions_answered'] == 1
    assert client.post(path, json={**payload, 'submission_id': str(uuid4())}).status_code == 409
    assert client.post(path, json={**payload, 'dont_know': False, 'answer': 'あ'}).status_code == 409


@pytest.mark.parametrize('extra', [ {'answer': ''}, {'answer': ' '}, {'answer': 'x' * 4001},
    {'answer': 'あ', 'dont_know': True}, {'answer': 'not a choice'}, {'answer': 'あ', 'submission_id': 'invalid'}])
def test_invalid_answers(client, extra):
    state = start(client)
    response = client.post(f'/api/assessments/{state["assessment_id"]}/answers', json={
        'question_id': state['question']['id'], 'submission_id': str(uuid4()), **extra})
    assert response.status_code == 422
    assert client.get(f'/api/assessments/{state["assessment_id"]}').json()['questions_answered'] == 0


def test_unknown_and_expired_assessment(client):
    assert client.get(f'/api/assessments/{uuid4()}').status_code == 404
    state = start(client)
    engine = client.app.state.assessment
    saved = engine.repository.get(UUID(state['assessment_id']))
    saved.updated_at = 0
    with engine.repository.connection() as db:
        db.execute('UPDATE assessments SET state_json=? WHERE id=?', (saved.model_dump_json(), state['assessment_id']))
    assert client.get(f'/api/assessments/{state["assessment_id"]}').status_code == 410


def test_persistence_resume_completion_and_tutor_integration(settings, provider):
    with TestClient(create_app(settings, provider)) as client:
        state = skip(client, start(client)).json()
    with TestClient(create_app(settings, provider)) as client:
        resumed = client.get(f'/api/assessments/{state["assessment_id"]}').json()
        assert resumed['question'] == state['question']
        assert resumed['questions_answered'] == 1
        for _ in range(3):
            resumed = skip(client, resumed).json()
        profile = resumed['result']
    with TestClient(create_app(settings, provider)) as client:
        assert client.get(f'/api/assessments/{state["assessment_id"]}/result').json() == profile
        session_id = client.post('/api/sessions').json()['session_id']
        result = client.post('/api/chat', json={'session_id': session_id, 'message': 'Teach me', 'learner_id': profile['learner_id']})
        assert result.status_code == 200
        assert 'Application placement evidence' in provider.calls[-1]['instructions']
        assert 'Absolute Beginner' in provider.calls[-1]['instructions']
        assert 'hiragana' in provider.calls[-1]['instructions']
        # Legacy client without learner_id still works, without a profile injected.
        assert client.post('/api/chat', json={'session_id': session_id, 'message': 'Hello'}).status_code == 200
        assert 'Application placement evidence' not in provider.calls[-1]['instructions']


def semantic_payload(score=.75):
    return {'score': score, 'meaning_correct': True, 'grammar_correct': False, 'naturalness': .6,
            'acceptable_alternative': True, 'feedback_internal': 'Meaning is clear; review the particle.', 'detected_errors': ['particle_usage']}


def test_semantic_partial_credit_and_minimal_prompt():
    provider = MockProvider(json.dumps(semantic_payload()))
    question = next(q for q in QuestionBank.load().items if q.evaluation == 'semantic')
    result = asyncio.run(AnswerEvaluator(provider, 1).evaluate(question,
        AnswerRequest(question_id=question.id, submission_id=uuid4(), answer='私は学生だよ')))
    assert result.score == .75 and result.method == 'llm'
    assert result.detail.meaning_correct and not result.detail.grammar_correct
    call = provider.calls[0]
    assert len(call['messages']) == 1
    payload = json.loads(call['messages'][0].content)
    assert set(payload) == {'question', 'expected_meanings_or_answers', 'criteria', 'learner_answer'}
    assert 'Never assign a learner level' in call['instructions']


def test_known_alternative_is_local():
    provider = MockProvider()
    question = next(q for q in QuestionBank.load().items if 'I studied Japanese yesterday' in q.prompt)
    result = asyncio.run(AnswerEvaluator(provider, 1).evaluate(question,
        AnswerRequest(question_id=question.id, submission_id=uuid4(), answer='私は昨日日本語を勉強した。')))
    assert result.score == 1 and result.method == 'deterministic' and not provider.calls


@pytest.mark.parametrize('raw', ['garbage', '{}', '[]', json.dumps(semantic_payload(1.2)),
    json.dumps({**semantic_payload(), 'level': 'N1'}), json.dumps({**semantic_payload(), 'meaning_correct': 'yes'})])
def test_bad_evaluation_unavailable_not_wrong(raw):
    question = next(q for q in QuestionBank.load().items if q.evaluation == 'semantic')
    result = asyncio.run(AnswerEvaluator(MockProvider(raw), 1).evaluate(question,
        AnswerRequest(question_id=question.id, submission_id=uuid4(), answer='different response')))
    assert result.score is None and result.weight == 0 and result.method == 'unavailable'


def test_timeout_unavailable():
    class SlowProvider:
        async def generate(self, **kwargs):
            await asyncio.Event().wait()
    question = next(q for q in QuestionBank.load().items if q.evaluation == 'semantic')
    result = asyncio.run(AnswerEvaluator(SlowProvider(), .01).evaluate(question,
        AnswerRequest(question_id=question.id, submission_id=uuid4(), answer='different response')))
    assert result.score is None


def test_romaji_is_reduced_evidence():
    question = next(q for q in QuestionBank.load().items if q.romaji_answers)
    result = asyncio.run(AnswerEvaluator(MockProvider(), 1).evaluate(question,
        AnswerRequest(question_id=question.id, submission_id=uuid4(), answer=question.romaji_answers[0])))
    assert result.score == 1 and result.romaji_used and result.weight == .5


def simulate(boundary, *, uneven=False):
    bank = QuestionBank.load()
    state = AssessmentState(assessment_id=uuid4(), learner_id=uuid4(), started_at=0, updated_at=0)
    reason = None
    while reason is None:
        question = select_question(state, bank)
        assert question is not None
        limit = {'vocabulary': 11, 'kanji': 2, 'sentence_construction': 9}.get(question.skill, 5) if uneven else boundary
        score = float(question.difficulty <= limit or (question.skill in SCRIPTS and boundary >= 0))
        state.evidence.append(evidence(question, score))
        reason = stopping_reason(state)
        assert len(state.evidence) <= MAX_QUESTIONS
    return state, build_profile(state, reason)


@pytest.mark.parametrize('boundary,low,high', [(3, 2.5, 4.5), (6, 4, 7), (9, 7, 10), (14, 10, 14)])
def test_simulated_learner_ranges_and_coverage(boundary, low, high):
    state, profile = simulate(boundary)
    assert low <= profile.overall_score <= high
    assert all(profile.skills[s].evidence_count >= 2 for s in MAJORS)
    assert len({e.question.id for e in state.evidence}) == len(state.evidence)
    assert 16 <= len(state.evidence) <= 30
    if boundary == 14:
        assert any(e.question.difficulty >= 8 for e in state.evidence[:10])
        assert any('ceiling' in note for note in profile.limitations)


def test_dynamic_lengths_and_uneven_skills():
    beginner, low = simulate(-1)
    n5, _ = simulate(3)
    advanced, _ = simulate(14)
    assert len(beginner.evidence) == 4 < len(n5.evidence) < len(advanced.evidence)
    _, mixed = simulate(6, uneven=True)
    assert mixed.skills['vocabulary'].difficulty_estimate > mixed.skills['kanji'].difficulty_estimate + 3
    assert mixed.skills['sentence_construction'].difficulty_estimate > mixed.skills['kanji'].difficulty_estimate + 3
    assert 'while strengthening' in mixed.recommended_starting_point


def test_difficulty_increases_and_decreases():
    state, _ = simulate(6)
    for skill in ['vocabulary', 'kanji']:
        levels = [e.question.difficulty for e in state.evidence if e.question.skill == skill]
        if skill == 'vocabulary': assert any(b > a for a,b in zip(levels, levels[1:]))
        if skill == 'kanji': assert any(b < a for a,b in zip(levels, levels[1:]))


def test_confidence_penalizes_inconsistency_and_unavailable():
    questions = [q for q in QuestionBank.load().items if q.skill == 'vocabulary']
    consistent = [evidence(q, float(q.difficulty <= 6)) for q in questions]
    inconsistent = [evidence(q, float(q.difficulty >= 6)) for q in questions]
    assert estimate('vocabulary', consistent).confidence > estimate('vocabulary', inconsistent).confidence
    lucky = estimate('vocabulary', [evidence(questions[-1], 1)])
    assert lucky.confidence < .3
    prior = estimate('vocabulary', consistent[:4]).difficulty_estimate
    assert abs(estimate('vocabulary', consistent[:4] + [evidence(questions[0], 0)]).difficulty_estimate - prior) < 3
    unavailable = evidence(questions[-1], None, weight=0)
    assert estimate('vocabulary', consistent + [unavailable]).difficulty_estimate == estimate('vocabulary', consistent).difficulty_estimate
    assert estimate('vocabulary', consistent + [unavailable]).confidence < estimate('vocabulary', consistent).confidence


def test_maximum_even_without_semantic_evidence():
    state, _ = simulate(14)
    for item in state.evidence:
        item.evaluation = Evaluation(score=None, weight=0, method='unavailable')
    while len(state.evidence) < MAX_QUESTIONS:
        state.evidence.append(state.evidence[0])
    assert stopping_reason(state) == 'maximum_questions'
    profile = build_profile(state, 'maximum_questions')
    assert profile.overall_score is None and profile.confidence == 0


def test_database_failure_does_not_break_chat(settings, provider, tmp_path):
    settings.assessment_db_path = str(tmp_path)  # A directory is not a valid SQLite file.
    with TestClient(create_app(settings, provider)) as client:
        assert client.post('/api/assessments', json={}).status_code == 503
        session = client.post('/api/sessions').json()['session_id']
        assert client.post('/api/chat', json={'session_id': session, 'message': 'hello'}).status_code == 200


def test_save_failure_leaves_question_unanswered(client, monkeypatch):
    state = start(client)
    repository = client.app.state.assessment.repository
    def fail(*args):
        raise TutorError('assessment_storage', 'Unavailable', 503)
    monkeypatch.setattr(repository, 'save_answer', fail)
    assert skip(client, state).status_code == 503
    saved = client.get(f'/api/assessments/{state["assessment_id"]}').json()
    assert saved['questions_answered'] == 0 and saved['question'] == state['question']


def test_atomic_write_rolls_back_on_profile_failure(client):
    state = start(client)
    repository = client.app.state.assessment.repository
    for _ in range(3): state = skip(client, state).json()
    # Force the final INSERT to fail after UPDATE and answer INSERT; all must roll back.
    with repository.connection() as db:
        db.execute("CREATE TRIGGER fail_profile BEFORE INSERT ON learner_profiles BEGIN SELECT RAISE(ABORT, 'test failure'); END")
    assert skip(client, state).status_code == 503
    saved = repository.get(UUID(state['assessment_id']))
    assert saved.status == 'in_progress' and len(saved.evidence) == 3
    with repository.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM assessment_answers').fetchone()[0] == 3


def test_empty_bank_and_exhaustion(client):
    engine = client.app.state.assessment
    original = engine.bank
    engine.bank = QuestionBank([])
    assert client.post('/api/assessments', json={}).status_code == 503
    engine.bank = QuestionBank(original.items[:1])
    state = start(client)
    result = skip(client, state).json()['result']
    assert result['stopping_reason'] == 'bank_exhausted' and result['confidence_label'] == 'Low'


def test_concurrent_requests_cannot_double_score(settings):
    async def run():
        bank = QuestionBank.load()
        repository = AssessmentRepository(settings.assessment_db_path)
        repository.initialize(bank)
        entered, release = asyncio.Event(), asyncio.Event()
        class WaitingEvaluator:
            async def evaluate(self, question, request):
                entered.set()
                await release.wait()
                return Evaluation(score=1, method='deterministic')
        engine = AssessmentEngine(repository, bank, WaitingEvaluator(), 86400)
        state = engine.start(StartRequest())
        key = UUID(state['assessment_id'])
        request = AnswerRequest(question_id=state['question']['id'], submission_id=uuid4(), answer='あ')
        first = asyncio.create_task(engine.answer(key, request))
        await entered.wait()
        with pytest.raises(TutorError) as caught:
            await engine.answer(key, request)
        assert caught.value.code == 'assessment_busy'
        release.set()
        await first
        assert len(repository.get(key).evidence) == 1
    asyncio.run(run())


def test_question_candidate_validation():
    bank = QuestionBank.load()
    with pytest.raises(ValueError): bank.validated_candidates('not json')
    with pytest.raises(ValueError): bank.validated_candidates(json.dumps([bank.items[0].model_dump()]))
    candidate = bank.items[0].model_dump()
    candidate.update(id='new-item', source='generated')
    assert bank.validated_candidates(json.dumps([candidate]))[0].source == 'generated'
    assert len(bank.items) == 68  # Validation does not silently publish a generated item.


def test_choice_order_is_stable_without_mutating_bank():
    bank = QuestionBank.load()
    original = list(bank.items[0].choices)
    states = [AssessmentState(assessment_id=uuid4(), learner_id=uuid4(), started_at=0, updated_at=0) for _ in range(12)]
    orders = [tuple(select_question(state, bank).choices) for state in states]
    assert len(set(orders)) > 1
    assert select_question(states[0], bank).choices == list(orders[0])
    assert bank.items[0].choices == original


def test_unavailable_free_answer_is_persisted_without_scoring(client, provider):
    state = start(client)
    engine = client.app.state.assessment
    saved = engine.load(UUID(state['assessment_id']))
    saved.current = next(q for q in engine.bank.items if q.evaluation == 'semantic' and q.skill == 'sentence_construction')
    with engine.repository.connection() as db:
        db.execute('UPDATE assessments SET state_json=? WHERE id=?', (saved.model_dump_json(), state['assessment_id']))
    provider.raw = 'bad json'
    response = client.post(f'/api/assessments/{state["assessment_id"]}/answers', json={
        'question_id': saved.current.id, 'submission_id': str(uuid4()), 'answer': 'A different attempt'})
    assert response.status_code == 200
    assert 'did not count as incorrect' in response.json()['notice']
    persisted = engine.load(saved.assessment_id)
    skill = estimate('sentence_construction', persisted.evidence)
    assert skill.evidence_count == 0 and skill.unavailable_count == 1 and skill.difficulty_estimate is None


def test_self_report_is_not_used_in_result_scoring():
    state, profile = simulate(3)
    changed = state.model_copy(update={'self_report': 'N4'})
    second = build_profile(changed, profile.stopping_reason)
    assert second.overall_score == profile.overall_score
    assert second.skills == profile.skills


def test_optimistic_lock_rejects_stale_writer(client):
    state = start(client)
    engine = client.app.state.assessment
    stale = engine.load(UUID(state['assessment_id']))
    assert skip(client, state).status_code == 200
    stale.evidence.append(evidence(stale.current, 1))
    stale.version += 1
    with pytest.raises(TutorError) as caught:
        engine.repository.save_answer(stale, expected_version=0)
    assert caught.value.code == 'assessment_conflict'
    assert len(engine.load(stale.assessment_id).evidence) == 1


def test_completed_answer_replay_does_not_create_second_profile(client):
    state = start(client)
    for _ in range(3): state = skip(client, state).json()
    body = {'question_id': state['question']['id'], 'submission_id': str(uuid4()), 'dont_know': True}
    path = f'/api/assessments/{state["assessment_id"]}/answers'
    first = client.post(path, json=body)
    second = client.post(path, json=body)
    assert first.status_code == second.status_code == 200
    assert second.json()['replayed'] and second.json()['questions_answered'] == 4
    assert first.json()['result'] == second.json()['result']


def test_invalid_bank_preserves_ordinary_chat(settings, provider, monkeypatch):
    def fail():
        raise ValueError('Invalid item')
    monkeypatch.setattr(QuestionBank, 'load', fail)
    with TestClient(create_app(settings, provider)) as client:
        assert client.post('/api/assessments', json={}).status_code == 503
        key = client.post('/api/sessions').json()['session_id']
        assert client.post('/api/chat', json={'session_id': key, 'message': 'Teach Japanese'}).status_code == 200
