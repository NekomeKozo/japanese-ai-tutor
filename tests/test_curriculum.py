import copy
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.curriculum.catalog import CATALOG, validate_catalog
from app.curriculum.content import MAX_LESSON_CONTEXT_BYTES, lesson_context
from app.curriculum.planner import ability, build_plan, prerequisite_status, rank_candidates, strategy
from app.curriculum.schemas import PlanRequest
from app.main import create_app
from tests.test_assessment import skip, start
from tests.test_learning_memory import create, profile, record

NOW=datetime.now(timezone.utc)


def mature(client,estimate=4):
    data=profile(client,create(client))
    data.update(profile_source='placement_assessment',estimated_level='N4',overall_score=estimate,placement_confidence=.7)
    for state in data['skills'].values():
        state.update(estimate=estimate,confidence=.7,placement_evidence=4)
    return data


def topic(data,key,status='needs_review',score=.2,age=1):
    state={'topic_key':key,'display_name':CATALOG[key].title,'skill':CATALOG[key].skill,'status':status,
        'encounters':4,'correct_count':0 if score<.6 else 4,'incorrect_count':4 if score<.6 else 0,
        'recent_score':score,'last_seen_at':(NOW-timedelta(days=age)).isoformat()}
    data['topic_memory']=[t for t in data['topic_memory'] if t['topic_key']!=key]+[state]
    data['weak_topics']=[t for t in data['topic_memory'] if t['status']=='needs_review']
    data['strong_topics']=[t for t in data['topic_memory'] if t['status']=='strong']
    return state


def request(data,**kwargs):
    return PlanRequest(learner_id=data['learner_id'],**kwargs)


def ranks(data,**kwargs):
    return {r['topic_id']:r for r in rank_candidates(data,request(data,**kwargs),{},NOW)}


def plan_api(client,learner,**kwargs):
    response=client.post('/api/curriculum/plan',json={'learner_id':learner,**kwargs})
    assert response.status_code==200,response.text
    return response.json()


def path(learner,plan,suffix=''):
    return f'/api/learners/{learner}/study/{plan["session_id"]}{suffix}'


def activate(client,learner,plan):
    assert client.post(path(learner,plan,'/start')).status_code==200
    activity=plan['activities'][0]
    url=path(learner,plan,f'/activities/{activity["activity_id"]}')
    return activity,url


def test_catalog_reuses_learning_ids_and_is_acyclic():
    from app.learner.catalog import TOPICS
    validate_catalog()
    assert len(CATALOG)==63
    assert set(CATALOG)<=set(TOPICS)
    assert sum(t.skill=='grammar' for t in CATALOG.values())==26


def test_new_learner_gets_honest_foundations(client):
    data=profile(client,create(client))
    result=build_plan(data,request(data),now=NOW)
    assert result['activities'] and 'introductory' in result['note']
    assert all(a['difficulty']<=1 for a in result['activities'])
    assert not any(a['topic_id']=='grammar_nagara' for a in result['activities'])


def test_phase_two_only_profile_can_plan(client):
    state=start(client)
    for _ in range(4): state=skip(client,state).json()
    plan=plan_api(client,state['learner_id'])
    assert plan['activities'] and plan['status']=='planned'


def test_weak_and_repeated_error_priority(client):
    data=mature(client)
    baseline=ranks(data)['particle_ni_destination']['priority']
    state=topic(data,'particle_ni_destination','learning',0)
    state.update(encounters=1,incorrect_count=1)
    single=ranks(data)['particle_ni_destination']['priority']
    assert single-baseline<2
    topic(data,'particle_ni_destination')
    weak=ranks(data)['particle_ni_destination']['priority']
    assert weak>single+3
    data['common_mistakes']=[{'mistake_key':'particle_ni_destination','status':'active','recent_occurrences':3}]
    repeated=ranks(data)['particle_ni_destination']
    assert repeated['priority']>weak and repeated['reason_codes'][0]=='repeated_recent_errors'


def test_strong_lower_priority_and_old_review_gains_priority(client):
    data=mature(client)
    topic(data,'vocab_daily','learning',.7)
    normal=ranks(data)['vocab_daily']['priority']
    topic(data,'vocab_daily','strong',1)
    assert ranks(data)['vocab_daily']['priority']<normal
    young=ranks(data)['vocab_daily']['priority']
    topic(data,'vocab_daily','strong',1,age=45)
    assert ranks(data)['vocab_daily']['priority']>young


def test_repetition_penalty_and_underrepresented_skill(client):
    data=mature(client)
    req=request(data)
    baseline={x['topic_id']:x for x in rank_candidates(data,req,{},NOW)}
    changed={x['topic_id']:x for x in rank_candidates(data,req,{'topic_sessions':{'verb_forms':4},'skill_minutes':{'grammar':55,'vocabulary':30,'reading':10,'kanji':5}},NOW)}
    assert changed['verb_forms']['priority']<baseline['verb_forms']['priority']-4
    assert changed['kanji_numbers']['priority']>baseline['kanji_numbers']['priority']


def test_missing_and_weak_prerequisites_block_advanced_material(client):
    data=mature(client,0)
    data['skills']['grammar'].update(estimate=5,confidence=0,placement_evidence=0)
    assert 'grammar_nagara' not in ranks(data)
    topic(data,'verb_masu_stem','needs_review',.1)
    assert 'grammar_nagara' not in ranks(data)
    topic(data,'verb_masu_stem','learning',.7)
    partial=ranks(data)['grammar_nagara']['priority']
    topic(data,'verb_masu_stem','strong',1)
    assert ranks(data)['grammar_nagara']['priority']>partial


def test_prerequisite_exposure_is_not_readiness(client):
    data=mature(client,0)
    state=topic(data,'verb_masu_stem','learning',.7)
    state['recent_score']=None
    assert prerequisite_status('verb_masu_stem',data,{'verb_masu_stem':state})=='unknown'


def test_goals_affect_ranking_without_difficulty_jumps(client):
    data=mature(client,2)
    ordinary=ranks(data)['vocab_transport']['priority']
    data['preferences']['primary_goal']='travel'
    assert ranks(data)['vocab_transport']['priority']>ordinary
    data['preferences']['primary_goal']='JLPT_N1'
    assert all(a['difficulty']<=3 for a in build_plan(data,request(data),now=NOW)['activities'])


@pytest.mark.parametrize('focus',['grammar','vocabulary','kanji','reading'])
def test_focus_is_respected(client,focus):
    data=mature(client)
    plan=build_plan(data,request(data,session_type=focus),now=NOW)
    assert all(a['skill']==focus for a in plan['activities'])


@pytest.mark.parametrize('minutes',[5,7,10,15,20,30,45,60])
def test_time_budget_and_activity_counts(client,minutes):
    data=mature(client)
    result=build_plan(data,request(data,available_minutes=minutes),now=NOW)
    assert sum(a['duration_minutes'] for a in result['activities'])==result['estimated_minutes']<=minutes
    assert all(2<=a['duration_minutes']<=12 for a in result['activities'])
    if minutes<10: assert len(result['activities'])==1
    if minutes>=30: assert len({a['skill'] for a in result['activities']})>=3
    assert all(a['reason_codes'] and a['reason'] for a in result['activities'])
    assert all('priority' not in a for a in result['activities'])


def test_struggling_strong_and_returning_strategies(client):
    data=mature(client)
    base=strategy(data,request(data),NOW)['target_review_ratio']
    for state in data['skills'].values(): state.update(recent_count=8,recent_average=.2)
    weak=strategy(data,request(data),NOW)['target_review_ratio']
    assert weak>base
    for state in data['skills'].values(): state.update(recent_average=.98)
    assert strategy(data,request(data),NOW)['target_review_ratio']<base
    data['last_activity_at']=(NOW-timedelta(days=60)).isoformat()
    assert strategy(data,request(data),NOW)['target_review_ratio']>base-.05


def test_uneven_skill_profile_and_determinism(client):
    data=mature(client,7)
    data['skills']['grammar']['estimate']=2
    result=build_plan(data,request(data,available_minutes=60),now=NOW)
    assert result==build_plan(copy.deepcopy(data),request(data,available_minutes=60),now=NOW)
    assert all(a['difficulty']<=3 for a in result['activities'] if a['skill']=='grammar')
    assert ability(data,'vocabulary')>ability(data,'grammar')
    vocab=build_plan(data,request(data,session_type='vocabulary'),now=NOW)
    assert any(a['difficulty']>=7 for a in vocab['activities'])


def test_plan_resumes_even_when_request_changes_and_survives_restart(settings,provider):
    with TestClient(create_app(settings,provider)) as client:
        learner=create(client)
        first=plan_api(client,learner,available_minutes=10)
        assert plan_api(client,learner,available_minutes=60)==first
        assert provider.calls==[]
    with TestClient(create_app(settings,provider)) as client:
        assert client.get(path(learner,first)).json()==first
        assert client.get(f'/api/learners/{learner}/study/active').json()==first


def test_template_completion_events_retry_recap_and_feedback_loop(client,provider):
    learner=create(client)
    plan=plan_api(client,learner,available_minutes=5,session_type='vocabulary')
    activity,url=activate(client,learner,plan)
    opened=client.post(url+'/open')
    assert opened.status_code==200 and 'reference_answers' not in opened.text and 'answers' not in opened.json()['response']
    answer=CATALOG[activity['topic_id']].answer
    body={'submission_id':str(uuid4()),'answer':answer}
    done=client.post(url+'/complete',json=body)
    assert done.status_code==200 and done.json()['score']==1
    assert client.post(url+'/complete',json=body).json()==done.json()
    assert client.post(url+'/complete',json={**body,'answer':'different'}).status_code==409
    state=profile(client,learner)
    assert state['skills']['vocabulary']['learning_count']==1
    assert state['topic_memory'][0]['correct_count']==1
    finished=client.post(path(learner,plan,'/complete')).json()
    assert finished['status']=='completed' and finished['recap']['strong_performance']==[activity['title']]
    assert provider.calls==[]
    events=client.get(f'/api/learners/{learner}/activity').json()
    assert sum(e['event_type']=='performance' for e in events)==1
    next_plan=plan_api(client,learner,available_minutes=5,session_type='review')
    assert next_plan['session_id']!=plan['session_id']
    assert next_plan['activities'][0]['purpose']=='review'


def test_skip_is_not_success_and_finish_requires_terminal_activities(client):
    learner=create(client)
    plan=plan_api(client,learner,available_minutes=10)
    activity,url=activate(client,learner,plan)
    assert client.post(path(learner,plan,'/complete')).status_code==409
    assert client.post(url+'/skip').status_code==200
    assert client.post(url+'/skip').status_code==200
    state=profile(client,learner)
    assert all(s['learning_count']==0 for s in state['skills'].values())
    assert state['topic_memory']==[]


def test_malformed_or_wrong_topic_lesson_keeps_plan_and_retries_once(client,provider):
    learner=create(client)
    plan=plan_api(client,learner,available_minutes=5,session_type='grammar')
    _,url=activate(client,learner,plan)
    provider.raw='{}'
    assert client.post(url+'/open').status_code==502
    assert len(provider.calls)==2
    saved=client.get(path(learner,plan)).json()
    assert saved['activities'][0]['status']=='not_started'
    assert profile(client,learner)['topic_memory']==[]


def lesson_payload(activity,**kwargs):
    return {'topic_id':activity['topic_id'],'difficulty':activity['difficulty'],'title':'Practice',
        'explanation':'Form a polite statement.','examples':['学生です。'],
        'prompt':'Say: I am a teacher.','choices':[],'answers':['先生です。'],
        'evaluation':'semantic','feedback':'です makes a polite statement.',**kwargs}


def test_generated_lesson_reuses_provider_evaluator_and_compact_context(client,provider):
    learner=create(client)
    plan=plan_api(client,learner,available_minutes=5,session_type='grammar')
    activity,url=activate(client,learner,plan)
    provider.raw=json.dumps(lesson_payload(activity))
    response=client.post(url+'/open')
    assert response.status_code==200
    assert '先生です。' not in response.text
    assert len(provider.calls)==1
    assert len(provider.calls[0]['messages'][0].content.encode())<=MAX_LESSON_CONTEXT_BYTES
    assert client.post(url+'/open').status_code==200 and len(provider.calls)==1
    body={'submission_id':str(uuid4()),'answer':'先生です。'}
    assert client.post(url+'/complete',json=body).json()['score']==1
    assert len(provider.calls)==1  # Exact semantic reference uses existing deterministic path.


def test_generated_identity_mismatch_rejected(client,provider):
    learner=create(client)
    plan=plan_api(client,learner,available_minutes=5,session_type='grammar')
    activity,url=activate(client,learner,plan)
    provider.raw=json.dumps(lesson_payload(activity,topic_id='grammar_nagara'))
    assert client.post(url+'/open').status_code==502


def test_provider_failure_and_grading_failure_preserve_activity(client,provider):
    from app.errors import TutorError
    learner=create(client)
    plan=plan_api(client,learner,available_minutes=5,session_type='grammar')
    activity,url=activate(client,learner,plan)
    provider.error=TutorError('provider_unavailable','Test provider unavailable',503)
    assert client.post(url+'/open').status_code==503
    assert client.get(path(learner,plan)).json()['status']=='in_progress'
    provider.error=None; provider.raw=json.dumps(lesson_payload(activity))
    assert client.post(url+'/open').status_code==200
    provider.error=TutorError('provider_unavailable','Test provider unavailable',503)
    assert client.post(url+'/complete',json={'submission_id':str(uuid4()),'answer':'別の答え'}).status_code==503
    assert profile(client,learner)['skills']['grammar']['learning_count']==0
    assert client.get(path(learner,plan)).json()['activities'][0]['status']=='in_progress'


def test_activity_result_and_memory_rollback_atomically(client):
    learner=create(client)
    plan=plan_api(client,learner,available_minutes=5,session_type='vocabulary')
    activity,url=activate(client,learner,plan)
    assert client.post(url+'/open').status_code==200
    with client.app.state.learners.repository.connection() as db:
        db.execute("CREATE TRIGGER fail_curriculum BEFORE INSERT ON learning_events WHEN NEW.event_type='performance' BEGIN SELECT RAISE(ABORT,'test'); END")
    response=client.post(url+'/complete',json={'submission_id':str(uuid4()),'answer':CATALOG[activity['topic_id']].answer})
    assert response.status_code==503
    assert client.get(path(learner,plan)).json()['activities'][0]['status']=='in_progress'
    assert profile(client,learner)['skills']['vocabulary']['learning_count']==0


def test_activity_ownership_order_and_abandon(client):
    a,b=create(client),create(client)
    plan=plan_api(client,a,available_minutes=10)
    first=plan['activities'][0]
    assert client.get(path(b,plan)).status_code==404
    assert client.post(path(b,plan,'/start')).status_code==404
    assert client.post(path(a,plan,f'/activities/{first["activity_id"]}/open')).status_code==409
    activate(client,a,plan)
    second=plan['activities'][1]
    assert client.post(path(a,plan,f'/activities/{second["activity_id"]}/open')).status_code==409
    assert client.post(path(a,plan,'/abandon')).json()['status']=='abandoned'
    assert plan_api(client,a)['session_id']!=plan['session_id']


@pytest.mark.parametrize('patch',[{'available_minutes':0},{'available_minutes':61},{'available_minutes':2.5},{'available_minutes':True},{'session_type':'voice'},{'requested_focus':'N1'}])
def test_invalid_plan_request(client,patch):
    learner=create(client)
    assert client.post('/api/curriculum/plan',json={'learner_id':learner,**patch}).status_code==422


def test_context_excludes_lifetime_history(client):
    data=mature(client)
    data['history']=['large private history']*10000
    activity=build_plan(data,request(data),now=NOW)['activities'][0]
    context=lesson_context(activity,data)
    assert len(context.encode())<=MAX_LESSON_CONTEXT_BYTES
    assert 'history' not in context and 'initial_placement' not in context


def test_phase_three_broad_weak_topic_influences_specific_candidates(client):
    data=mature(client)
    before=ranks(data)['vocab_daily']['priority']
    data['weak_topics']=[{'topic_key':'other_vocabulary','skill':'vocabulary'}]
    after=ranks(data)['vocab_daily']['priority']
    assert after>before


def test_returning_learner_gap_is_not_erased_by_opening_chat(client):
    learner=create(client)
    record(client,learner,1,topic='vocab_taberu',skill='vocabulary')
    old=(NOW-timedelta(days=60)).isoformat()
    with client.app.state.learners.repository.connection() as db:
        db.execute('UPDATE learning_events SET created_at=? WHERE learner_id=?',(old,learner))
    client.post(f'/api/learners/{learner}/sessions')
    plan=plan_api(client,learner)
    assert plan['strategy']['returning_learner'] is True


def test_empty_candidate_fallback_and_review_shortage_are_honest(client):
    data=mature(client)
    fallback=build_plan(data,request(data,session_type='grammar'),now=NOW,catalog={})
    assert fallback['activities'] and fallback['estimated_minutes']<=30
    fresh=profile(client,create(client))
    plan=build_plan(fresh,request(fresh,session_type='review'),now=NOW)
    assert plan['strategy']['review_ratio']==0 and 'limited' in plan['note']


def test_v2_migration_preserves_profiles_preferences_events_and_transcripts(settings,provider):
    from tests.test_learning_memory import saved_request
    with TestClient(create_app(settings,provider)) as client:
        learner=create(client)
        record(client,learner,0)
        body=saved_request(client,learner)
        assert client.post('/api/chat',json=body).status_code==200
        assert client.patch(f'/api/learners/{learner}/preferences',json={'primary_goal':'travel'}).status_code==200
    with sqlite3.connect(settings.assessment_db_path) as db:
        db.execute('DROP TABLE study_activities'); db.execute('DROP TABLE study_sessions')
        db.execute('PRAGMA user_version=2')
        tables=('learner_state','learner_profiles','skill_state','learner_topics','mistake_state','learning_events','tutor_sessions','conversation_turns')
        before={table:db.execute(f'SELECT * FROM {table} ORDER BY 1,2').fetchall() for table in tables}
    for _ in range(2):
        with TestClient(create_app(settings,provider)) as client:
            assert profile(client,learner)['preferences']['primary_goal']=='travel'
            assert client.get(f'/api/learners/{learner}/sessions/{body["session_id"]}').json()['interaction_count']==1
        with sqlite3.connect(settings.assessment_db_path) as db:
            assert db.execute('PRAGMA user_version').fetchone()[0]==6
            assert all(db.execute(f'SELECT * FROM {table} ORDER BY 1,2').fetchall()==rows for table,rows in before.items())


def test_curriculum_migration_failure_rolls_back(settings,provider,monkeypatch):
    with TestClient(create_app(settings,provider)) as client: learner=create(client)
    with sqlite3.connect(settings.assessment_db_path) as db:
        db.execute('DROP TABLE study_activities'); db.execute('DROP TABLE study_sessions'); db.execute('PRAGMA user_version=2')
    import app.curriculum.migrations as migrations
    monkeypatch.setattr(migrations,'DDL',[*migrations.DDL,'INVALID SQL'])
    with TestClient(create_app(settings,provider)) as client:
        assert client.post('/api/curriculum/plan',json={'learner_id':learner}).status_code==503
        assert client.post('/api/sessions').status_code==201
    with sqlite3.connect(settings.assessment_db_path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==2
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='study_sessions'").fetchone()
        assert db.execute('SELECT COUNT(*) FROM learner_state').fetchone()[0]==1


def test_study_reset_is_scoped_and_restores_foreign_key_integrity(client):
    from app.learner.reset import reset_learner
    a,b=create(client),create(client)
    plan_api(client,a); other=plan_api(client,b)
    reset_learner(client.app.state.learners.repository,a,a)
    assert client.get(f'/api/learners/{a}/study/active').json() is None
    assert client.get(path(b,other)).status_code==200
    with client.app.state.learners.repository.connection() as db: assert db.execute('PRAGMA foreign_key_check').fetchall()==[]


def test_completed_activity_feedback_survives_restart(settings,provider):
    with TestClient(create_app(settings,provider)) as client:
        learner=create(client)
        plan=plan_api(client,learner,available_minutes=5,session_type='kanji')
        activity,url=activate(client,learner,plan)
        assert client.post(url+'/open').status_code==200
        body={'submission_id':str(uuid4()),'answer':CATALOG[activity['topic_id']].distractors[0]}
        result=client.post(url+'/complete',json=body).json()
        assert result['score']==0
    with TestClient(create_app(settings,provider)) as client:
        assert client.post(url+'/complete',json=body).json()==result
        plan=client.post(path(learner,plan,'/complete')).json()
        assert plan['recap']['needs_review']==[activity['title']]
        assert profile(client,learner)['skills']['kanji']['learning_count']==1


def test_placement_weaknesses_win_over_strong_kana(client):
    data=mature(client,2)
    for skill in ('hiragana','katakana'):
        data['skills'][skill]['estimated_level']='Strong on sampled items'
        topic(data,skill,'learning',1)
    topic(data,'kanji_reading',score=.1)
    topic(data,'reading_meaning',score=.1)
    data['common_mistakes']=[{'mistake_key':'kanji_reading','status':'active','recent_occurrences':4}]
    plan=build_plan(data,request(data),now=NOW)
    assert plan['activities'][0]['purpose']=='review'
    assert 'kanji_reading' in {a['topic_id'] for a in plan['activities']}
    assert not {'hiragana','katakana'} & {a['skill'] for a in plan['activities']}


@pytest.mark.parametrize('persona',['A','B','C','D'])
def test_requested_learner_simulations(client,persona):
    data=mature(client,2 if persona=='A' else 5 if persona=='B' else 8)
    history={}
    if persona=='A':
        topic(data,'particle_ni_destination',score=.1)
        topic(data,'verb_forms','strong',1)
        data['skills']['hiragana']['estimated_level']='Strong on sampled items'
        data['preferences']['primary_goal']='JLPT_N4'
    elif persona=='B':
        topic(data,'kanji_reading',score=.1)
        topic(data,'verb_forms','strong',1)
        history={'topic_sessions':{'verb_forms':4},'skill_minutes':{'grammar':55,'vocabulary':30,'reading':10,'kanji':5}}
    elif persona=='C':
        topic(data,'verb_forms','familiar',.8,age=60)
        topic(data,'vocab_daily','familiar',.8,age=60)
        topic(data,'kanji_reading','familiar',.8,age=60)
        data['last_activity_at']=(NOW-timedelta(days=60)).isoformat()
    else: data['skills']['grammar']['estimate']=2
    plan=build_plan(data,request(data),history,now=NOW)
    if persona=='A':
        assert 'particle_ni_destination' in {a['topic_id'] for a in plan['activities']}
        assert max(a['difficulty'] for a in plan['activities'])<=3
    elif persona=='B':
        assert 'kanji_reading' in {a['topic_id'] for a in plan['activities']}
        assert sum(a['skill']=='grammar' for a in plan['activities'])<3
    elif persona=='C':
        assert plan['strategy']['name']=='review_heavy'
        assert plan['strategy']['review_ratio']>=.6
    else:
        assert all(a['difficulty']<=3 for a in plan['activities'] if a['skill']=='grammar')


def test_content_difficulty_mismatch_and_blank_fields_are_rejected(client,provider):
    learner=create(client)
    plan=plan_api(client,learner,available_minutes=5,session_type='grammar')
    activity,url=activate(client,learner,plan)
    provider.raw=json.dumps(lesson_payload(activity,difficulty=14))
    assert client.post(url+'/open').status_code==502
    provider.raw=json.dumps(lesson_payload(activity,answers=['']))
    assert client.post(url+'/open').status_code==502


def test_unknown_learner_and_completed_session_do_not_leak_or_restart(client):
    assert client.post('/api/curriculum/plan',json={'learner_id':str(uuid4())}).status_code==404
    learner=create(client)
    plan=plan_api(client,learner,available_minutes=5)
    _,url=activate(client,learner,plan)
    client.post(url+'/skip')
    finished=client.post(path(learner,plan,'/complete')).json()
    assert finished['recap']['practiced']==[] and finished['recap']['skipped_count']==1
    assert client.post(path(learner,plan,'/complete')).json()==finished
    assert client.post(path(learner,plan,'/start')).status_code==409


def test_generation_finishing_after_skip_cannot_reopen_activity(client,provider):
    import asyncio
    from app.errors import TutorError
    learner=create(client)
    plan=plan_api(client,learner,available_minutes=5,session_type='grammar')
    activity,_=activate(client,learner,plan)
    service=client.app.state.curriculum
    async def race():
        entered,release=asyncio.Event(),asyncio.Event()
        async def generate(**kwargs):
            entered.set(); await release.wait()
            return json.dumps(lesson_payload(activity))
        provider.generate=generate
        task=asyncio.create_task(service.open_activity(learner,plan['session_id'],activity['activity_id']))
        await entered.wait()
        service.skip(learner,plan['session_id'],activity['activity_id'])
        release.set()
        with pytest.raises(TutorError) as error: await task
        assert error.value.status==409
    asyncio.run(race())
    assert profile(client,learner)['topic_memory']==[]
    assert service.get(learner,plan['session_id'])['activities'][0]['status']=='skipped'
    assert not service.busy


def test_cancelled_generation_leaves_plan_and_lock_usable(client,provider):
    import asyncio
    learner=create(client)
    plan=plan_api(client,learner,available_minutes=5,session_type='grammar')
    activity,url=activate(client,learner,plan)
    service=client.app.state.curriculum
    original=provider.generate
    async def run():
        entered=asyncio.Event()
        async def generate(**kwargs):
            entered.set(); await asyncio.Event().wait()
        provider.generate=generate
        task=asyncio.create_task(service.open_activity(learner,plan['session_id'],activity['activity_id']))
        await entered.wait(); task.cancel()
        with pytest.raises(asyncio.CancelledError): await task
    asyncio.run(run())
    assert not service.busy
    assert profile(client,learner)['topic_memory']==[]
    provider.generate=original; provider.raw=json.dumps(lesson_payload(activity))
    assert client.post(url+'/open').status_code==200


def test_plan_schema_checks_budget_before_persistence(client):
    from app.curriculum.schemas import StudyPlan
    from pydantic import ValidationError
    data=mature(client)
    plan=build_plan(data,request(data),now=NOW)
    for activity in plan['activities']: activity['activity_id']=str(uuid4())
    assert StudyPlan.model_validate(plan)
    plan['estimated_minutes']=60
    with pytest.raises(ValidationError): StudyPlan.model_validate(plan)


def test_two_app_instances_resume_one_active_plan(settings,provider):
    from concurrent.futures import ThreadPoolExecutor
    with TestClient(create_app(settings,provider)) as first, TestClient(create_app(settings,provider)) as second:
        learner=create(first)
        with ThreadPoolExecutor(max_workers=2) as pool:
            futures=[pool.submit(plan_api,c,learner,available_minutes=20) for c in (first,second)]
            results=[f.result() for f in futures]
        assert results[0]['session_id']==results[1]['session_id']
        with sqlite3.connect(settings.assessment_db_path) as db:
            assert db.execute('SELECT COUNT(*) FROM study_sessions').fetchone()[0]==1
