import copy
import json
import sqlite3
from dataclasses import replace
from datetime import datetime,timedelta,timezone
from uuid import uuid4
import pytest
from fastapi.testclient import TestClient
from app.main import create_app
from app.review.scheduler import ReviewScheduler
from app.review.ratings import rating
from app.review.policy import POLICY
from app.review.service import ReviewService,bootstrap,identity
from app.review.content import supported,lesson
from app.mastery.schemas import Evidence
from app.learner.schemas import LearningEvent
from app.learner.events import process_event
from app.learner.catalog import TOPICS
from tests.test_learning_memory import create
from tests.test_curriculum import plan_api

NOW=datetime(2026,1,1,12,tzinfo=timezone.utc)
STRONG=dict(score=.95,confidence=.85,status='strong')
WEAK=dict(score=.45,confidence=.1,status='learning')

class Clock:
    def __init__(self,now=NOW): self.value=now
    def now(self): return self.value

def ev(score=1,**changes):
    fields=dict(event_id='event',learner_id='learner',topic_id='vocab_taberu',topic_type='vocabulary',dimension='production',
        score=score,difficulty=2,learner_level=2,evidence_type='production',activity_type='recall',source='curriculum',
        context_id='context',hint_used=False,quality=1,timestamp=NOW)
    fields.update(changes); return Evidence(**fields)

@pytest.mark.parametrize('score,expected',[(0,'again'),(.44,'again'),(.45,'hard'),(.6,'hard'),(.69,'hard'),(.7,'good'),(.89,'good'),(.9,'easy'),(1,'easy')])
def test_rating_partial_credit(score,expected):
    assert rating(ev(score),STRONG)==expected

@pytest.mark.parametrize('changes,expected',[(dict(hint_used=True),'hard'),(dict(hint_used=None),'good'),(dict(answer_revealed=True),'hard'),
    (dict(evidence_type='recognition'),'good'),(dict(quality=.35),'good'),(dict(difficulty=0,learner_level=6),'good')])
def test_independence_rating(changes,expected): assert rating(ev(**changes),STRONG)==expected

@pytest.mark.parametrize('score',[float('nan'),float('inf'),-1,1.1])
def test_bad_score(score):
    with pytest.raises(ValueError): ev(score)

def test_initial_and_determinism():
    scheduler=ReviewScheduler()
    first=scheduler.schedule_new_item(None,ev(),WEAK,NOW)
    assert first==scheduler.schedule_new_item(None,ev(),WEAK,NOW)
    assert first['interval_days']<=3.2
    poor=scheduler.schedule_new_item(None,ev(0),WEAK,NOW)
    assert poor['interval_days']<first['interval_days']
    assert poor['state']=='learning' and first['algorithm_version']==1

def history(count=8,mastery=STRONG):
    s=ReviewScheduler(); state=None; now=NOW
    for _ in range(count):
        state=s.process_review(state,ev(),mastery,now); now=datetime.fromisoformat(state['due_at'])
    return state,now

def test_success_growth_easy_good_hard_confidence():
    old,now=history(3)
    scheduler=ReviewScheduler()
    results=[scheduler.process_review(old,ev(score),STRONG,now) for score in (.6,.8,1)]
    assert results[0]['interval_days'] <= results[1]['interval_days'] < results[2]['interval_days']
    assert results[1]['interval_days']>old['interval_days']
    high,_=history(15); low,_=history(15,WEAK)
    assert high['interval_days']>30 and high['interval_days']>low['interval_days']
    assert low['interval_days']<=7.4

def test_lapse_relearning_and_persistent_difficulty():
    old,now=history(); s=ReviewScheduler(); original=copy.deepcopy(old)
    failed=s.process_review(old,ev(0),STRONG,now)
    assert old==original
    assert failed['state']=='relearning' and failed['lapse_count']==1
    assert failed['interval_days']<old['interval_days']/4
    for i in range(4):
        now=datetime.fromisoformat(failed['due_at']); failed=s.process_review(failed,ev(0),WEAK,now)
    assert failed['persistent_difficulty'] and failed['interval_days']>=1

def test_same_day_cap_and_needs_review():
    s=ReviewScheduler(); state=None; now=NOW
    for i in range(3):
        state=s.process_review(state,ev(0),WEAK,now); now=datetime.fromisoformat(state['due_at'])
    assert state['interval_days']>=1
    old,now=history()
    result=s.process_review(old,ev(.8),dict(STRONG,status='needs_review'),now)
    assert result['interval_days']<=1

def test_utc_clock_and_backward_guard():
    s=ReviewScheduler(); state=s.process_review(None,ev(),WEAK,NOW)
    with pytest.raises(ValueError): s.process_review(state,ev(),WEAK,NOW-timedelta(seconds=1))
    with pytest.raises(ValueError): s.process_review(None,ev(),WEAK,NOW.replace(tzinfo=None))
    assert s.process_review(None,ev(),WEAK,NOW.astimezone(timezone(timedelta(hours=8))))==state

@pytest.fixture
def setup(client,monkeypatch):
    clock=Clock(); learner=create(client)
    monkeypatch.setattr('app.learner.events.now_iso',lambda:clock.now().isoformat())
    client.app.state.reviews.clock=clock; client.app.state.curriculum.reviews.clock=clock
    return learner,clock

def record(client,learner,topic='vocab_taberu',dim='production',score=1,**extra):
    event=LearningEvent(event_id=uuid4(),learner_id=learner,event_type='performance',topic_key=topic,
        skill=TOPICS[topic].skill,score=score,difficulty=2,source='curriculum')
    context=dict(dimension=dim,evidence_type='production' if dim=='production' else 'recall',
        activity_type='review',context_id=str(uuid4()),hint_used=False,learner_level=2)
    if dim in ('on_reading','kun_reading'): context['reading_context']='学生' if dim=='on_reading' else '学ぶ'
    context.update(extra)
    with client.app.state.learners.repository.connection() as db:
        db.execute('BEGIN IMMEDIATE'); process_event(db,event,metadata_extra={'mastery':context})
    return event

def saved(client,learner,topic='vocab_taberu',dim='production'):
    with client.app.state.learners.repository.connection() as db:
        row=db.execute('SELECT state_json FROM review_schedules WHERE learner_id=? AND topic_id=? AND dimension=?',(learner,topic,dim)).fetchone()
    return json.loads(row[0]) if row else None

def test_unseen_exposure_and_duplicate(client,setup,provider):
    learner,clock=setup
    assert client.app.state.reviews.get_due_reviews(learner)['due_count']==0
    event=record(client,learner)
    original=saved(client,learner)
    with client.app.state.learners.repository.connection() as db:
        assert not process_event(db,event)
        from app.review.service import process_event as repeat
        repeat(db,event.event_id)
    assert saved(client,learner)==original
    assert not provider.calls

@pytest.mark.parametrize('topic,dim',[('vocab_taberu','recognition'),('vocab_taberu','meaning'),('vocab_taberu','reading'),('vocab_taberu','production'),
    ('tai_form','recognition'),('tai_form','understanding'),('tai_form','application'),('tai_form','production'),
    ('kanji_gaku','recognition'),('kanji_gaku','meaning'),('kanji_gaku','on_reading'),('kanji_gaku','kun_reading')])
def test_dimensions_schedule_independently(client,setup,topic,dim):
    learner,clock=setup; record(client,learner,topic,dim)
    assert saved(client,learner,topic,dim)
    with client.app.state.learners.repository.connection() as db:
        assert db.execute('SELECT count(*) FROM review_schedules WHERE learner_id=?',(learner,)).fetchone()[0]==1

def test_synthetic_a_f_uneven_dimensions(client,setup):
    learner,clock=setup
    for topic,dims in [('vocab_toshokan',('meaning','reading','production')),('kanji_gaku',('meaning','recognition','on_reading'))]:
        for i,d in enumerate(dims): record(client,learner,topic,d,score=.6 if i==2 else 1)
        assert saved(client,learner,topic,dims[2])['interval_days'] < saved(client,learner,topic,dims[0])['interval_days']

def test_queue_future_due_suspension_timezone(client,setup):
    learner,clock=setup; record(client,learner,score=0)
    service=client.app.state.reviews
    assert service.get_due_reviews(learner)['due_count']==0
    clock.value+=timedelta(hours=1)
    due=service.get_due_reviews(learner); assert due['due_count']==1
    key=due['items'][0]['review_id']; service.suspend_review(learner,key)
    assert service.get_due_reviews(learner)['due_count']==0
    service.resume_review(learner,key); assert service.get_due_reviews(learner)['due_count']==1
    assert service.forecast(learner,'Asia/Manila')['today']==1
    assert client.get(f'/api/learners/{learner}/reviews/forecast?timezone=not-real').status_code==422
    assert client.get(f'/api/learners/{uuid4()}/reviews/due').status_code==404
    assert client.get(f'/api/learners/{learner}/reviews/due?minutes=100').status_code==422

def seed_backlog(client,learner):
    from app.mastery.catalog import topic_type
    from app.mastery.policy import DIMENSIONS
    for topic in TOPICS:
        kind=topic_type(topic)
        if not kind: continue
        dim='production' if kind!='kanji' else 'meaning'
        if supported(topic,dim): record(client,learner,topic,dim,score=0)

def test_backlog_capacity_long_absence_priority(client,setup):
    learner,clock=setup; seed_backlog(client,learner)
    before=client.app.state.mastery.curriculum_signals(learner)
    clock.value+=timedelta(days=90); service=client.app.state.reviews
    short=service.get_due_reviews(learner,10); longer=service.get_due_reviews(learner,30)
    assert short['backlog'] and short['due_count']>20
    assert short['selected_minutes']<=10 and len(longer['items'])>len(short['items'])
    assert short==service.get_due_reviews(learner,10)
    assert len({i['topic_id'] for i in short['items']})==len(short['items'])
    assert all(i['priority']=='high' for i in short['items'])
    assert client.app.state.mastery.curriculum_signals(learner)==before
    plan=plan_api(client,learner,available_minutes=10)
    assert plan['strategy']['name']=='review_heavy' and plan['estimated_minutes']<=10
    assert any(a['review_schedule_id'] for a in plan['activities'])
    assert service.get_due_reviews(learner,10)['due_count']==short['due_count']

def start_review(client,learner):
    plan=plan_api(client,learner,available_minutes=10,session_type='review')
    base=f'/api/learners/{learner}/study/{plan["session_id"]}'
    assert client.post(base+'/start').status_code==200
    activity=plan['activities'][0]; path=base+'/activities/'+activity['activity_id']
    return base,path,activity

def test_full_review_atomic_retry_restart(client,setup,settings,provider):
    learner,clock=setup; record(client,learner,score=0); clock.value+=timedelta(hours=1)
    base,path,a=start_review(client,learner)
    assert a['review_schedule_id'] and a['focus_dimension']=='production'
    assert '食べる' not in a['title']
    opened=client.post(path+'/open'); assert opened.status_code==200,opened.text
    assert 'たべる' not in opened.text
    assert '食べる' not in opened.text
    body=dict(submission_id=str(uuid4()),answer='食べる')
    result=client.post(path+'/complete',json=body); assert result.status_code==200,result.text
    assert result.json()['score']==1 and result.json()['next_review']
    state=saved(client,learner); assert state['review_count']==2
    assert client.post(path+'/complete',json=body).json()==result.json()
    assert saved(client,learner)==state
    assert client.app.state.mastery.get_topic_mastery(learner,'vocab_taberu')['evidence_count']==2
    assert client.post(base+'/complete').status_code==200
    assert not provider.calls
    with TestClient(create_app(settings,provider)) as other: assert saved(other,learner)==state

def test_skip_and_stale_review(client,setup):
    learner,clock=setup; record(client,learner,score=0); clock.value+=timedelta(hours=1)
    base,path,a=start_review(client,learner); previous=saved(client,learner)
    assert client.post(path+'/skip').status_code==200
    assert saved(client,learner)==previous and client.app.state.reviews.get_due_reviews(learner)['due_count']==1
    client.post(base+'/complete')
    base,path,a=start_review(client,learner)
    record(client,learner)
    assert client.post(path+'/open').status_code==409

def test_provider_failure_is_not_failure(client,setup,provider):
    from app.errors import TutorError
    learner,clock=setup; record(client,learner,'tai_form','production',score=0); clock.value+=timedelta(hours=1)
    base,path,a=start_review(client,learner); previous=saved(client,learner,'tai_form')
    provider.error=TutorError('provider_error','Unavailable',503)
    assert client.post(path+'/open').status_code==503
    assert saved(client,learner,'tai_form')==previous
    with client.app.state.learners.repository.connection() as db:
        assert db.execute('SELECT count(*) FROM review_attempts').fetchone()[0]==1

def test_transaction_failure_rolls_back_all(client,setup):
    learner,clock=setup
    with client.app.state.learners.repository.connection() as db:
        db.execute("CREATE TRIGGER fail_schedule BEFORE INSERT ON review_schedules BEGIN SELECT RAISE(ABORT,'test'); END")
    with pytest.raises(Exception): record(client,learner)
    assert saved(client,learner) is None
    assert client.app.state.mastery.get_topic_mastery(learner,'vocab_taberu')['score'] is None

def test_rebuild_preserves_history_and_suspension(client,setup):
    learner,clock=setup
    for _ in range(4):
        record(client,learner); clock.value=datetime.fromisoformat(saved(client,learner)['due_at'])
    previous=saved(client,learner); service=client.app.state.reviews
    service.reschedule_topic(learner,'vocab_taberu'); rebuilt=saved(client,learner)
    assert {k:v for k,v in previous.items() if k!='version'}=={k:v for k,v in rebuilt.items() if k!='version'}

def test_v4_bootstrap_stagger_and_preservation(client,setup):
    learner,clock=setup; seed_backlog(client,learner)
    repo=client.app.state.learners.repository
    with repo.connection() as db:
        db.execute('DELETE FROM review_attempts'); db.execute('DELETE FROM review_schedules')
        before=db.execute('SELECT * FROM topic_mastery').fetchall()
        bootstrap(db,NOW,learner)
        dates=[datetime.fromisoformat(r[0]) for r in db.execute('SELECT due_at FROM review_schedules')]
        assert min(dates)>NOW and len({d.date() for d in dates})>=3
        assert max(sum(d.date()==date for d in dates) for date in {d.date() for d in dates})<=10
        assert db.execute('SELECT * FROM topic_mastery').fetchall()==before
        count=len(dates); bootstrap(db,NOW,learner)
        assert db.execute('SELECT count(*) FROM review_schedules').fetchone()[0]==count

def test_virtual_load_100_items_six_weeks():
    scheduler=ReviewScheduler(); cards={}; totals=[]
    # Introduce 10 items/day for ten days: learner behavior does not inject 100 at once.
    for day in range(42):
        now=NOW+timedelta(days=day); reviewed=0
        if day<10:
            for j in range(10):
                key=day*10+j; cards[key]=scheduler.process_review(None,ev(topic_id=f'virtual_{key}'),STRONG,now)
        for key,state in list(cards.items()):
            if datetime.fromisoformat(state['due_at'])<=now:
                cards[key]=scheduler.process_review(state,ev(topic_id=f'virtual_{key}'),STRONG,now); reviewed+=1
        totals.append(reviewed)
    assert len(cards)==100 and max(totals)<80 and sum(totals)>100
    assert min(s['interval_days'] for s in cards.values())>3

def test_v4_real_migration_and_rollback(settings,provider,monkeypatch):
    with TestClient(create_app(settings,provider)) as c:
        learner=create(c); record(c,learner)
    with sqlite3.connect(settings.assessment_db_path) as db:
        db.execute('DROP TABLE review_attempts'); db.execute('DROP TABLE review_schedules')
        db.execute('PRAGMA user_version=4')
        tables=[r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")]
        before={t:db.execute(f'SELECT * FROM {t}').fetchall() for t in tables}
    from app.review import service
    original=service.bootstrap
    def fail(*args): raise ValueError('Injected bootstrap failure')
    monkeypatch.setattr(service,'bootstrap',fail)
    with TestClient(create_app(settings,provider)) as c:
        assert c.get(f'/api/learners/{learner}/reviews/due').status_code==503
    with sqlite3.connect(settings.assessment_db_path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==4
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='review_schedules'").fetchone()
    monkeypatch.setattr(service,'bootstrap',original)
    for _ in range(2):
        with TestClient(create_app(settings,provider)) as c:
            assert c.get(f'/api/learners/{learner}/reviews/due').status_code==200
        with sqlite3.connect(settings.assessment_db_path) as db:
            assert db.execute('PRAGMA user_version').fetchone()[0]==5
            assert {t:db.execute(f'SELECT * FROM {t}').fetchall() for t in tables}==before
            assert db.execute('SELECT count(*) FROM review_schedules').fetchone()[0]==1

def test_grading_failure_and_stale_submission_do_not_commit(client,setup,provider):
    learner,clock=setup; record(client,learner,'vocab_taberu','meaning',score=0); clock.value+=timedelta(hours=1)
    base,path,a=start_review(client,learner)
    assert client.post(path+'/open').status_code==200
    previous=saved(client,learner,'vocab_taberu','meaning')
    provider.raw='invalid JSON'
    body=dict(submission_id=str(uuid4()),answer='some paraphrase')
    assert client.post(path+'/complete',json=body).status_code==503
    assert saved(client,learner,'vocab_taberu','meaning')==previous
    record(client,learner,'vocab_taberu','meaning',score=.75)
    assert client.post(path+'/complete',json=dict(body,answer='to eat')).status_code==409

def test_review_transaction_and_conflict_guards(client,setup):
    learner,clock=setup; record(client,learner,score=0); clock.value+=timedelta(hours=1)
    base,path,a=start_review(client,learner); assert client.post(path+'/open').status_code==200
    before=saved(client,learner)
    with client.app.state.learners.repository.connection() as db:
        db.execute("CREATE TRIGGER fail_attempt BEFORE INSERT ON review_attempts BEGIN SELECT RAISE(ABORT,'test'); END")
    body=dict(submission_id=str(uuid4()),answer='たべる')
    assert client.post(path+'/complete',json=body).status_code==503
    assert saved(client,learner)==before
    with client.app.state.learners.repository.connection() as db:
        assert db.execute('SELECT status FROM study_activities WHERE activity_id=?',(a['activity_id'],)).fetchone()[0]=='in_progress'
        db.execute('DROP TRIGGER fail_attempt')
    assert client.post(path+'/complete',json=body).status_code==200
    assert client.post(path+'/complete',json=dict(body,answer='different')).status_code==409

def test_utc_local_day_boundaries(client,setup):
    learner,clock=setup; record(client,learner)
    service=client.app.state.reviews
    clock.value=NOW.replace(hour=15,minute=55) # Manila 23:55, still UTC Jan 1.
    key=identity(learner,'vocab_taberu','production')
    with client.app.state.learners.repository.connection() as db:
        db.execute('UPDATE review_schedules SET due_at=? WHERE schedule_id=?',((clock.value+timedelta(minutes=10)).isoformat(),key))
    assert service.forecast(learner,'Asia/Manila')['today']==0
    assert service.forecast(learner,'Asia/Manila')['tomorrow']==1
    assert service.forecast(learner,'UTC')['today']==1
    assert service.get_due_reviews(learner)['due_count']==0
    clock.value+=timedelta(minutes=11)
    assert service.get_due_reviews(learner)['due_count']==1

def test_overdue_priority_and_bounded_influence(client,setup):
    learner,clock=setup
    for topic in ('vocab_taberu','vocab_iku'): record(client,learner,topic,score=0)
    clock.value+=timedelta(days=1)
    with client.app.state.learners.repository.connection() as db:
        db.execute('UPDATE review_schedules SET due_at=? WHERE topic_id=?',((clock.value-timedelta(days=14)).isoformat(),'vocab_iku'))
    result=client.app.state.reviews.get_due_reviews(learner,10)
    assert result['items'][0]['topic_id']=='vocab_iku'
    assert result['items'][0]['priority']=='high'

def test_recognition_grows_less_and_missing_mastery_safe():
    old,now=history(2)
    s=ReviewScheduler(); recognition=s.process_review(old,ev(evidence_type='recognition'),STRONG,now)
    production=s.process_review(old,ev(),STRONG,now)
    assert recognition['interval_days']<production['interval_days']
    assert s.process_review(None,ev(),{},NOW)['interval_days']<=3.2

def test_production_and_kanji_fixed_content_varies():
    for topic,dim in [('vocab_taberu','production'),('vocab_toshokan','reading'),('kanji_gaku','on_reading')]:
        activity=dict(topic_id=topic,focus_dimension=dim,review_variant=0,difficulty=2)
        first=lesson(activity); second=lesson(dict(activity,review_variant=1))
        assert first.prompt!=second.prompt and first.answers==second.answers and first.evaluation=='fixed'
    assert not supported('kanji_gaku','production')

def test_clock_absence_does_not_change_state(client,setup):
    learner,clock=setup; record(client,learner); before=saved(client,learner)
    clock.value+=timedelta(days=90)
    client.app.state.reviews.get_due_reviews(learner)
    assert saved(client,learner)==before

def test_suspension_keeps_practice_mastery_but_not_schedule(client,setup):
    learner,clock=setup; record(client,learner); service=client.app.state.reviews
    service.suspend_review(learner,identity(learner,'vocab_taberu','production'))
    previous=saved(client,learner); record(client,learner,score=0)
    assert saved(client,learner)==previous
    assert client.app.state.mastery.get_topic_mastery(learner,'vocab_taberu')['evidence_count']==2

def test_bootstrap_mixed_strength_respects_daily_capacity(client,setup):
    learner,clock=setup; seed_backlog(client,learner)
    with client.app.state.learners.repository.connection() as db:
        db.execute('DELETE FROM review_attempts'); db.execute('DELETE FROM review_schedules')
        for index,(topic,payload) in enumerate(db.execute('SELECT topic_id,state_json FROM topic_mastery ORDER BY topic_id').fetchall()):
            if index%2==0:
                value=json.loads(payload)
                for d in value['dimensions'].values():
                    if d['score'] is not None: d.update(score=.95,confidence=.85)
                db.execute('UPDATE topic_mastery SET state_json=? WHERE topic_id=?',(json.dumps(value),topic))
        bootstrap(db,NOW.replace(hour=23,minute=58),learner)
        dates=[datetime.fromisoformat(r[0]).date() for r in db.execute('SELECT due_at FROM review_schedules')]
        assert max(dates.count(d) for d in set(dates))<=10
