import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.jlpt.bank import Bank
from app.jlpt.schemas import Question, Start
from app.jlpt.scoring import evaluate, results
from app.jlpt.selection import select
from app.main import create_app
from tests.conftest import MockProvider
from tests.test_learning_memory import create, profile
from tests.test_postgres import pg_settings
from tests.test_staging import gated, login


@pytest.fixture(params=['sqlite', 'postgres'])
def storage_settings(request, settings):
    return settings if request.param == 'sqlite' else request.getfixturevalue('pg_settings')


def base(learner):
    return f'/api/learners/{learner}/jlpt'


def start(client, learner, **kwargs):
    return client.post(base(learner)+'/sessions', json={'request_id':str(uuid4()), **kwargs})


def submit(client, learner, state, answer=None, submission=None):
    q = state['question']
    correct = client.app.state.jlpt.bank.by_id[q['id']].answers[0]
    body = {'question_id':q['id'], 'submission_id':submission or str(uuid4()), 'answer':correct if answer is None else answer}
    return client.post(base(learner)+f'/sessions/{state["session_id"]}/answer', json=body), body


def counts(client, learner):
    with client.app.state.repository.connection() as db:
        return dict(db.execute('SELECT event_type,COUNT(*) FROM learning_events WHERE learner_id=? GROUP BY event_type',(learner,)))


def test_bank_coverage_validation_and_no_keys_in_public():
    bank = Bank.load()
    assert len(bank.items) == 80
    assert all(count == 10 for section in bank.catalog()['coverage'].values() for count in section.values())
    for q in bank.items:
        assert evaluate(q, q.answers[0]) == 1
        assert not {'answers','explanation','topic_id','dimension'} & q.public().keys()
    with pytest.raises(ValueError): Bank([bank.items[0],bank.items[0]])
    q = bank.items[0].model_dump()
    for changes in [{'answers':['invalid']},{'choices':['same','same']},{'topic_id':'unknown'},
                    {'status':'published'},{'level':'N3'},{'question_type':'reading_comprehension'}]:
        with pytest.raises(ValidationError): Question.model_validate({**q, **changes})
    reading = next(q for q in bank.items if not q.choices)
    assert evaluate(reading, '　'+reading.answers[0]+'。 ') == 1
    assert results([], {})['accuracy'] == 0


@pytest.mark.parametrize('level', ['N5','N4'])
@pytest.mark.parametrize('mode,section,count', [('quick','mixed',5),('standard','mixed',10),
    ('mock','mixed',20),('weakness','mixed',10), *[('focused',s,10) for s in ['vocabulary','kanji','grammar','reading']]])
def test_selection(level, mode, section, count):
    bank = Bank.load(); request = Start(level=level, mode=mode, section=section, request_id=uuid4())
    selected = select(bank, request, set(), {})
    assert len(selected)==count and len({q.id for q in selected})==count
    assert all(q.level==level and q.status=='approved' for q in selected)
    assert selected == select(bank, request, set(), {})
    if section=='mixed': assert len({q.section for q in selected})==4
    else: assert all(q.section==section for q in selected)
    if count<=10 and section=='mixed':
        assert not {q.id for q in selected} & {q.id for q in select(bank,request,{q.id for q in selected},{})}


def test_weakness_and_unapproved_questions():
    bank=Bank.load(); q=bank.items[0]
    selected=select(bank,Start(mode='weakness',request_id=uuid4()),set(),{q.topic_id:1})
    assert selected[0].topic_id==q.topic_id
    for status in ['candidate','reviewed','retired']:
        changed=Bank([item.model_copy(update={'status':status}) if item.id==q.id else item for item in bank.items])
        assert q.id not in {item.id for item in select(changed,Start(request_id=uuid4()),set(),{})}


def test_persistence_replay_score_exposure_and_placement(storage_settings):
    provider=MockProvider()
    with TestClient(create_app(storage_settings,provider)) as client:
        learner=create(client); before=profile(client,learner)
        request={'request_id':str(uuid4()),'mode':'quick'}
        state=client.post(base(learner)+'/sessions',json=request).json()
        url=base(learner)+f'/sessions/{state["session_id"]}'
        assert client.post(base(learner)+'/sessions',json=request).json()['session_id']==state['session_id']
        assert start(client,learner).status_code==409
        for i in range(5):
            response, body=submit(client,learner,state)
            assert response.status_code==200, response.text
            state=response.json(); assert state['feedback']['correct'] is True
            assert client.post(url+'/answer',json=body).json()['answered_count']==i+1
            assert client.post(url+'/answer',json={**body,'answer':'changed'}).status_code==409
        assert counts(client,learner)['performance']==5
        qid=state['feedback']['id']
        for _ in range(2): assert client.post(url+'/explanations/'+qid).status_code==200
        assert counts(client,learner)['concept_explained']==1
        assert counts(client,learner)['performance']==5
        state=client.post(url+'/finish').json()
        assert state['result']['accuracy']==100 and len(state['review'])==5
        assert client.post(url+'/finish').json()==state
        after=profile(client,learner)
        assert after['estimated_level']==before['estimated_level']
        assert after['initial_placement']==before['initial_placement']
        assert not provider.calls
    with TestClient(create_app(storage_settings,provider)) as client:
        assert client.get(url).json()==state
        assert client.get(base(learner)+'/history').json()[0]['accuracy']==100
        assert client.get(base(learner)+'/sessions/active').json() is None


def test_mock_privacy_expiry_and_snapshots(storage_settings):
    with TestClient(create_app(storage_settings,MockProvider())) as client:
        learner=create(client); service=client.app.state.jlpt
        now=datetime.now(timezone.utc); service.clock=lambda:now
        state=start(client,learner,mode='mock',timed=True).json()
        url=base(learner)+f'/sessions/{state["session_id"]}'
        qid=state['question']['id']; deadline=state['deadline_at']
        response,body=submit(client,learner,state); saved=response.json()
        assert saved['feedback'] is None and saved['review']==[] and saved['result'] is None
        assert counts(client,learner).get('performance',0)==0
        assert client.get(base(learner)+'/history').json()[0]['accuracy'] is None
        assert client.post(url+'/explanations/'+qid).status_code==409
        assert client.get(url).json()['deadline_at']==deadline
        service.bank=Bank([])  # Historical questions and scores must survive bank retirement.
        now+=timedelta(hours=2)
        state=client.get(url).json()
        assert state['status']=='completed' and state['remaining_seconds']==0
        assert state['result']['correct']==1 and state['result']['total']==20
        assert counts(client,learner)['performance']==1
        assert client.post(url+'/answer',json=body).json()['result']==state['result']
        assert client.post(url+'/finish').json()==state
        assert counts(client,learner)['performance']==1


def test_ownership_and_invalid_inputs(gated):
    login(gated); learner=create(gated); other=create(gated)
    state=start(gated,learner).json(); sid=state['session_id']
    assert gated.get(base(other)+f'/sessions/{sid}').status_code==404
    assert gated.post(base(other)+f'/sessions/{sid}/finish').status_code==404
    assert start(gated,other,level='N3').status_code==422
    assert start(gated,other,mode='focused').status_code==422
    assert start(gated,other,section='kanji',question_count=20).status_code==422
    assert submit(gated,learner,state,answer='')[0].status_code==422
    assert submit(gated,learner,state,answer='not a choice')[0].status_code==422
    gated.cookies.clear()
    assert gated.get(base(learner)+f'/sessions/{sid}').status_code in (401,403)


def test_atomic_concurrent_start_answer_and_finish(storage_settings):
    with TestClient(create_app(storage_settings,MockProvider())) as client:
        learner=create(client)
        with ThreadPoolExecutor(2) as pool:
            responses=list(pool.map(lambda _:start(client,learner), range(2)))
        assert sorted(r.status_code for r in responses)==[201,409]
        state=next(r.json() for r in responses if r.status_code==201)
        url=base(learner)+f'/sessions/{state["session_id"]}'
        with ThreadPoolExecutor(2) as pool:
            responses=list(pool.map(lambda _:submit(client,learner,state)[0], range(2)))
        assert sorted(r.status_code for r in responses)==[200,409]
        assert counts(client,learner)['performance']==1
        current=client.get(url).json()
        with ThreadPoolExecutor(2) as pool:
            answer=pool.submit(submit,client,learner,current)
            finish=pool.submit(client.post,url+'/finish')
            assert answer.result()[0].status_code in (200,409)
            assert finish.result().status_code==200
        assert client.get(url).json()['status']=='completed'
        assert counts(client,learner)['performance'] in (1,2)


def test_schema_6_migration_is_additive_and_atomic(storage_settings, monkeypatch):
    from app.jlpt import migrations
    from app.assessment.questions import QuestionBank
    original=migrations.migrate
    from app.audio_progress import migrations as audio_migrations
    audio_original=audio_migrations.migrate
    monkeypatch.setattr(audio_migrations,'migrate',lambda db:None)
    monkeypatch.setattr(migrations,'migrate',lambda db:None)
    with TestClient(create_app(storage_settings,MockProvider())) as client:
        learner=create(client); repo=client.app.state.repository
        with repo.connection() as db:
            assert db.execute('PRAGMA user_version').fetchone()[0]==6
            # A real Phase 8 catalog does not already contain the new N4 topics.
            from app.jlpt.topics import VOCAB, KANJI
            for item in VOCAB + KANJI:
                db.execute('DELETE FROM learning_topics WHERE topic_key=?', (item[0],))
            tables=['learner_state','skill_state','learning_events','conversation_states','review_schedules']
            before={table:db.execute(f'SELECT * FROM {table}').fetchall() for table in tables}
    def fail(db):
        original(db)
        raise ValueError('Simulated failure after DDL')
    monkeypatch.setattr(migrations,'migrate',fail)
    from app.errors import TutorError
    with pytest.raises(TutorError): repo.initialize(QuestionBank.load())
    with repo.connection() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==6
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='jlpt_sessions'").fetchone()
        assert not db.execute("SELECT 1 FROM learning_topics WHERE topic_key='vocab_kariru'").fetchone()
    monkeypatch.setattr(migrations,'migrate',original)
    monkeypatch.setattr(audio_migrations,'migrate',audio_original)
    for _ in range(2):
        repo.initialize(QuestionBank.load())
        with repo.connection() as db:
            assert db.execute('PRAGMA user_version').fetchone()[0]==8
            assert {table:db.execute(f'SELECT * FROM {table}').fetchall() for table in tables}==before
            assert db.execute("SELECT 1 FROM learning_topics WHERE topic_key='vocab_kariru'").fetchone()


def test_schema_7_repairs_missing_topics_and_preserves_saved_mock(storage_settings):
    from app.assessment.questions import QuestionBank
    from app.jlpt.topics import VOCAB, KANJI
    with TestClient(create_app(storage_settings,MockProvider())) as client:
        learner=create(client); service=client.app.state.jlpt; repo=client.app.state.repository
        now=datetime.now(timezone.utc); service.clock=lambda:now
        # Choose a reproducible mixed mock containing the previously missing topic.
        for seed in range(1,101):
            request=Start(level='N4',mode='mock',timed=True,request_id=UUID(int=seed))
            chosen=select(service.bank,request,set(),{})
            if any(q.topic_id=='vocab_kariru' for q in chosen[:5]): break
        else: pytest.fail('No mock containing target topic')
        state=client.post(base(learner)+'/sessions',json=request.model_dump(mode='json')).json()
        url=base(learner)+f'/sessions/{state["session_id"]}'
        for _ in range(5):
            response,_=submit(client,learner,state)
            assert response.status_code==200
            state=response.json()
        with repo.connection() as db:
            for item in VOCAB + KANJI:
                db.execute('DELETE FROM learning_topics WHERE topic_key=?',(item[0],))
            old=db.execute("SELECT * FROM learning_topics WHERE topic_key='particle_ni_destination'").fetchall()
            assert old
        assert counts(client,learner).get('performance',0)==0
        for _ in range(2): repo.initialize(QuestionBank.load())
        with repo.connection() as db:
            assert db.execute('PRAGMA user_version').fetchone()[0]==8
            assert db.execute("SELECT * FROM learning_topics WHERE topic_key='particle_ni_destination'").fetchall()==old
        restored=client.get(url).json()
        assert restored['answered_count']==5 and restored['deadline_at']==state['deadline_at']
        now+=timedelta(hours=5)
        finished=client.get(base(learner)+'/sessions/active')
        assert finished.status_code==200, finished.text
        result=finished.json()
        assert result['status']=='completed' and result['result']['correct']==5
        assert counts(client,learner)['performance']==5
        assert client.post(url+'/finish').json()['result']==result['result']
        assert counts(client,learner)['performance']==5


@pytest.mark.parametrize('level',['N5','N4'])
@pytest.mark.parametrize('section',['vocabulary','kanji','grammar','reading'])
def test_every_section_scores_and_integrates_evidence(client, provider, level, section):
    learner=create(client); state=start(client,learner,level=level,section=section,mode='focused').json()
    for i in range(10):
        q=client.app.state.jlpt.bank.by_id[state['question']['id']]
        answer=q.answers[0] if i%2==0 else next((c for c in q.choices if c not in q.answers),'まちがい')
        response,_=submit(client,learner,state,answer=answer)
        assert response.status_code==200, response.text
        state=response.json()
    state=client.post(base(learner)+f'/sessions/{state["session_id"]}/finish').json()
    assert state['result']['accuracy']==50 and state['result']['sections'][section]['correct']==5
    assert counts(client,learner)['performance']==10
    with client.app.state.repository.connection() as db:
        evidence=db.execute('SELECT payload FROM mastery_evidence WHERE learner_id=?',(learner,)).fetchall()
        scheduled=db.execute('SELECT COUNT(*) FROM review_schedules WHERE learner_id=?',(learner,)).fetchone()[0]
        if section=='reading':
            assert not evidence and scheduled==0  # General comprehension is not an invented word mastery item.
        else:
            assert evidence and scheduled>0
            assert all(json.loads(r[0])['source']=='quiz' for r in evidence)
    assert not provider.calls


def test_mock_abandon_does_not_reveal_or_score(client):
    learner=create(client); state=start(client,learner,mode='mock').json()
    submit(client,learner,state)
    url=base(learner)+f'/sessions/{state["session_id"]}'
    state=client.post(url+'/abandon').json()
    assert state['status']=='abandoned' and state['result'] is None and state['review']==[]
    assert client.post(url+'/finish').json()['status']=='abandoned'
    assert counts(client,learner).get('performance',0)==0


def test_evidence_failure_rolls_back_answer(client,monkeypatch):
    import app.jlpt.service as service
    learner=create(client); state=start(client,learner).json()
    def fail(*args,**kwargs): raise ValueError('Simulated failure')
    monkeypatch.setattr(service,'process_event',fail)
    assert submit(client,learner,state)[0].status_code==503
    saved=client.get(base(learner)+f'/sessions/{state["session_id"]}').json()
    assert saved['answered_count']==0 and saved['question']==state['question']
    assert counts(client,learner).get('performance',0)==0


def test_rag_authoring_private_candidate_only(settings, tmp_path):
    import asyncio
    from app.jlpt.authoring import candidate
    from app.knowledge.schemas import KnowledgeContext, SearchResult
    from app.knowledge.chunker import chunk_document
    from tests.test_knowledge import document
    q=Bank.load().items[0].model_dump()
    q.update(id='jlpt_candidate_test',prompt='In a drink order, what does 水 mean?',status='approved')
    context=KnowledgeContext(status='available', payload='synthetic private reference',
        results=[SearchResult(chunk=chunk_document(document())[0],score=1)])
    class Knowledge:
        async def context_for(self,*args,**kwargs): return context
    provider=MockProvider(json.dumps(q))
    args=dict(level=q['level'],section=q['section'],topic_id=q['topic_id'],root=tmp_path)
    path=asyncio.run(candidate(settings,provider,Knowledge(),Bank.load(),**args))
    saved=json.loads(path.read_text(encoding='utf-8'))
    assert path.parent==tmp_path/'knowledge_base'/'jlpt_candidates'
    assert saved['question']['status']=='candidate' and saved['question']['source_type']=='rag_candidate'
    assert saved['review_status']=='pending_manual_review' and saved['references']
    assert 'relative_path' not in path.read_text(encoding='utf-8') and 'private.md' not in path.read_text(encoding='utf-8')
    assert len(Bank.load().items)==80
    with pytest.raises(ValueError): asyncio.run(candidate(settings,provider,Knowledge(),Bank.load(),**args))
    settings.environment='staging'
    with pytest.raises(ValueError): asyncio.run(candidate(settings,provider,Knowledge(),Bank.load(),**args))
    settings.environment='development'; context.status='no_match'
    with pytest.raises(ValueError): asyncio.run(candidate(settings,provider,Knowledge(),Bank.load(),**args))
