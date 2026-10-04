"""Phase 11E: real scheduler/persistence, mocked providers only."""
import json
from datetime import datetime, timedelta
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.review.flashcards import card, eligible, catalog
from app.review.service import identity
from tests.test_reviews import setup, record, saved, STRONG, NOW, ev, Clock
from tests.test_learning_memory import create
from tests.test_staging import gated, login
from app.safeguards import COOKIE


def url(learner):
    return f'/api/learners/{learner}/reviews'


def due(client, learner, clock, topic='vocab_taberu', dimension='production'):
    record(client,learner,topic,dimension)
    clock.value = datetime.fromisoformat(saved(client,learner,topic,dimension)['due_at']) + timedelta(seconds=1)
    result = client.get(url(learner)+'/flashcards')
    assert result.status_code == 200, result.text
    return result.json()['items'][0]


def submit(client, learner, item, label='good', **changes):
    body = dict(submission_id=str(uuid4()),version=item['version'],rating=label)
    body.update(changes)
    return client.post(url(learner)+f"/{item['review_id']}/recall",json=body), body


@pytest.mark.parametrize('label',['again','hard','good','easy'])
def test_real_scheduler_persistence_receipt_and_history(client,setup,provider,monkeypatch,label):
    learner,clock=setup
    item=due(client,learner,clock)
    repository=client.app.state.reviews.repository
    with repository.connection() as db:
        mastery=db.execute('SELECT state_json FROM topic_mastery WHERE learner_id=?',(learner,)).fetchone()[0]
        count=db.execute('SELECT count(*) FROM mastery_evidence WHERE learner_id=?',(learner,)).fetchone()[0]
    before=saved(client,learner)
    from app.review.scheduler import ReviewScheduler
    calls=[]; original=ReviewScheduler.process_recall_rating
    def spy(self,*args): calls.append(args[-1]); return original(self,*args)
    monkeypatch.setattr(ReviewScheduler,'process_recall_rating',spy)
    response,body=submit(client,learner,item,label)
    assert response.status_code==200,response.text
    assert response.json()['completed'] and calls==[label]
    assert saved(client,learner)['version']==before['version']+1
    assert saved(client,learner)['last_rating']==label
    assert client.get(url(learner)+'/flashcards').json()['due_count']==0
    with repository.connection() as db:
        assert db.execute('SELECT state_json FROM topic_mastery WHERE learner_id=?',(learner,)).fetchone()[0]==mastery
        assert db.execute('SELECT count(*) FROM mastery_evidence WHERE learner_id=?',(learner,)).fetchone()[0]==count
        event=db.execute('SELECT event_type,score,metadata_json FROM learning_events WHERE event_id=?',(body['submission_id'],)).fetchone()
        assert event[0]=='flashcard_review_completed' and event[1] is None
        assert json.loads(event[2])['method']=='self_report'
    history=client.get(url(learner)+'/history').json()['items']
    assert len(history)==2 and history[0]['method']=='self_report' and history[1]['method']=='graded'
    assert 'card' not in history[0] and not provider.calls


def test_retry_restart_and_stale_version(client,setup,settings,provider):
    learner,clock=setup; item=due(client,learner,clock)
    response,body=submit(client,learner,item)
    state=saved(client,learner)
    with TestClient(create_app(settings,provider)) as restarted:
        restarted.app.state.reviews.clock=clock
        retry=restarted.post(url(learner)+f"/{item['review_id']}/recall",json=body)
        assert retry.json()==response.json()
        assert restarted.get(url(learner)+'/flashcards').json()['due_count']==0
    assert saved(client,learner)==state
    assert submit(client,learner,item)[0].status_code==409
    assert submit(client,learner,item,'easy',submission_id=body['submission_id'])[0].status_code==409


def test_isolation_and_empty(client,setup):
    learner,clock=setup; item=due(client,learner,clock)
    other=create(client)
    assert client.get(url(other)+'/flashcards').json()['items']==[]
    assert client.get(url(other)+'/history').json()['items']==[]
    assert submit(client,other,item)[0].status_code==404
    assert client.get(url(str(uuid4()))+'/flashcards').status_code==404
    fake=dict(item,review_id=str(uuid4()))
    assert submit(client,learner,fake)[0].status_code==404


def test_concurrent_retries_and_different_taps_are_atomic(client,setup):
    from concurrent.futures import ThreadPoolExecutor
    learner,clock=setup; item=due(client,learner,clock)
    body=dict(submission_id=str(uuid4()),version=item['version'],rating='good')
    path=url(learner)+f"/{item['review_id']}/recall"
    with ThreadPoolExecutor(max_workers=3) as pool:
        responses=list(pool.map(lambda _:client.post(path,json=body),range(3)))
    assert all(r.status_code==200 for r in responses)
    assert responses[0].json()==responses[1].json()==responses[2].json()
    assert saved(client,learner)['version']==item['version']+1
    assert len(client.get(url(learner)+'/history').json()['items'])==2
    assert submit(client,learner,item)[0].status_code==409


def test_not_due_and_invalid_review_identity(client,setup):
    learner,clock=setup; record(client,learner)
    item=dict(review_id=identity(learner,'vocab_taberu','production'),version=saved(client,learner)['version'])
    assert submit(client,learner,item)[0].status_code==409
    assert submit(client,learner,dict(item,review_id='bad'))[0].status_code==422


@pytest.mark.parametrize('changes',[dict(rating='excellent'),dict(rating=4),dict(version=0),dict(version='1'),dict(version=True),dict(submission_id='bad'),dict(score=1)])
def test_invalid_submissions(client,setup,changes):
    learner,clock=setup; item=due(client,learner,clock)
    original=saved(client,learner)
    assert submit(client,learner,item,**changes)[0].status_code==422
    assert saved(client,learner)==original


@pytest.mark.parametrize('topic,dimension,answer',[('vocab_taberu','reading','たべる'),('vocab_taberu','production','食べる'),('vocab_mizu','meaning','water'),('kanji_gaku','on_reading','がくせい'),('kanji_gaku','kun_reading','まなぶ'),('tai_form','understanding','want to do something')])
def test_dimension_mapping(topic,dimension,answer):
    result=card(topic,dimension)
    assert answer in result['back'] and result['audio_text']
    if dimension=='production': assert 'to eat' in result['front'] and '食べる' not in result['front']
    if dimension=='on_reading': assert '学生' in result['front'] and result['audio_text']=='学生'


def test_unmapped_content_filtered_before_session_limit(client,setup):
    learner,clock=setup
    for topic in ['particle_wa_vs_ga','verb_te_form','adjective_i_conjugation','verb_past_tense','copula_desu']:
        record(client,learner,topic,'production')
    item=due(client,learner,clock)
    clock.value += timedelta(days=8)
    result=client.get(url(learner)+'/flashcards').json()
    assert result['items'][0]['review_id']==item['review_id'] and result['unsupported_count']==5
    assert not eligible('tai_form','production') and not eligible('particle_wa_vs_ga','understanding')
    assert not eligible('kanji_kou','kun_reading')
    assert 'vocab_neko' not in catalog()
    assert client.get(url(learner)+'/due').json()['due_count']==6


def test_suspension_and_replay_preserve_existing_history(client,setup):
    learner,clock=setup; item=due(client,learner,clock)
    reviews=client.app.state.reviews
    reviews.suspend_review(learner,item['review_id'])
    assert submit(client,learner,item)[0].status_code==409
    reviews.resume_review(learner,item['review_id'])
    item=client.get(url(learner)+'/flashcards').json()['items'][0]
    assert submit(client,learner,item)[0].status_code==200
    state=saved(client,learner)
    reviews.reschedule_topic(learner,'vocab_taberu')
    replay=saved(client,learner)
    assert replay['due_at']==state['due_at'] and replay['review_count']==state['review_count']
    assert replay['version']==state['version']+1


def test_transaction_rolls_back_partial_save(client,setup,monkeypatch):
    learner,clock=setup; item=due(client,learner,clock)
    original=saved(client,learner)
    def fail(*args): raise RuntimeError('simulated transaction failure')
    with monkeypatch.context() as patch:
        patch.setattr('app.review.service.save',fail)
        assert submit(client,learner,item)[0].status_code==500
    assert saved(client,learner)==original
    assert len(client.get(url(learner)+'/history').json()['items'])==1


def test_authenticated_queue_submission_origin_and_rate_limit(gated,settings):
    learner=str(uuid4())
    assert gated.get(url(learner)+'/flashcards').status_code==401
    login(gated); learner=create(gated)
    clock=Clock(); gated.app.state.reviews.clock=clock
    item=due(gated,learner,clock)
    body=dict(submission_id=str(uuid4()),version=item['version'],rating='good')
    path=url(learner)+f"/{item['review_id']}/recall"
    assert gated.post(path,json=body,headers={'Origin':'https://evil.example'}).status_code==403
    token=gated.cookies.get(COOKIE)
    gated.cookies.clear(); login(gated)
    assert gated.get(url(learner)+'/flashcards').status_code==404
    assert gated.get(url(learner)+'/history').status_code==404
    assert gated.post(path,json=body).status_code==404
    gated.cookies.clear(); gated.cookies.set(COOKIE,token)
    settings.ai_rate_limit_per_hour=1
    assert gated.post(path,json=body).status_code==200
    assert gated.post(path,json=body).status_code==429
