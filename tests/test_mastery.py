import copy
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.mastery.calculator import calculate, measure, weight
from app.mastery.policy import DIMENSIONS, VERSION
from app.mastery.schemas import Evidence
from app.mastery.normalizer import normalize
from app.mastery.service import MasteryService, process_stored_event
from app.learner.events import process_event
from app.learner.schemas import LearningEvent
from tests.test_learning_memory import create, profile, saved_request
from tests.test_curriculum import plan_api, activate, lesson_payload, mature, request, ranks

START = datetime(2026, 1, 1, tzinfo=timezone.utc)


def evidence(index=0, score=1., dimension='production', kind='grammar', **changes):
    values = dict(event_id=f'e{index:04}', learner_id='learner', topic_id='tai_form', topic_type=kind,
        dimension=dimension, score=score, difficulty=2, learner_level=2, evidence_type='production',
        activity_type='sentence_construction', source='curriculum', context_id=f'question-{index}',
        hint_used=False, quality=1., timestamp=START+timedelta(days=index))
    values.update(changes)
    return Evidence(**values)


def series(count, **kwargs):
    return [evidence(i, **kwargs) for i in range(count)]


def varied(count=80, kind='grammar'):
    dimensions = list(DIMENSIONS[kind])
    types = ['recognition','comprehension','application','production','production']
    return [evidence(i, dimension=dimensions[i % len(dimensions)], kind=kind,
        evidence_type=types[i % len(dimensions)], activity_type=f'task-{i % 5}',
        reading_context='学生' if kind=='kanji' else None) for i in range(count)]


def test_unknown_and_first_success():
    state = calculate('tai_form', 'grammar', [])
    assert state['score'] is None and state['status']=='new'
    assert all(d['score'] is None for d in state['dimensions'].values())
    state = calculate('tai_form','grammar',series(1))
    assert state['status'] != 'strong' and state['confidence'] < .1
    assert state['score'] < .6


def test_repeated_success_failure_and_partial_credit():
    scores = [measure(series(10, score=value))['score'] for value in (0,.25,.5,.75,1)]
    assert scores == sorted(scores) and len(set(scores)) == 5
    assert measure(series(10))['score'] > measure(series(2))['score']
    assert measure(series(10, score=0))['score'] < measure(series(2, score=0))['score']


def test_production_hints_difficulty_and_source_quality():
    full = measure(series(6))
    assert full['score'] > measure(series(6,evidence_type='recognition'))['score']
    assert full['score'] > measure(series(6,hint_used=True))['score']
    assert full['confidence'] > measure(series(6,hint_used=None))['confidence']
    assert full['score'] < measure(series(6,difficulty=8))['score']
    assert full['confidence'] > measure(series(6,source='tutor_chat'))['confidence']
    assert weight(evidence(difficulty=14),0) <= 1.2
    assert measure([evidence(difficulty=14)])['score'] <= .58


def test_one_error_stability_decline_and_recovery():
    historical = series(25)
    before = measure(historical)
    assert before['score'] - measure(historical+[evidence(25,score=0)])['score'] <= .081
    failed = historical+[evidence(i,score=0) for i in range(25,29)]
    state = measure(failed)
    assert state['score'] > .6 and state['status']=='needs_review'
    recovered = measure(failed+[evidence(i) for i in range(29,48)])
    assert recovered['score'] > state['score'] and recovered['status'] != 'needs_review'
    assert measure(failed)['score'] > measure(series(4,score=0))['score']


def test_confidence_quantity_diversity_and_identical_questions():
    assert measure(series(12))['confidence'] > measure(series(1))['confidence']
    repeated = measure(series(40,evidence_type='recognition',context_id='same-question'))
    diverse = measure(varied(40))
    assert repeated['independent_count']==1 and repeated['confidence'] < .1
    assert diverse['confidence'] > measure(series(40,evidence_type='recognition'))['confidence']
    assert measure(series(20,score=.5))['status'] != 'strong'


@pytest.mark.parametrize('kind,dimension', [(kind,d) for kind,dims in DIMENSIONS.items() for d in dims])
def test_dimensions_are_separate(kind,dimension):
    state = calculate('topic',kind,series(8,kind=kind,dimension=dimension))
    assert state['dimensions'][dimension]['score'] is not None
    assert all(v['score'] is None for d,v in state['dimensions'].items() if d!=dimension)
    assert state['status'] != 'strong'


def test_synthetic_a_recognition_only_vocabulary():
    items = series(7,kind='vocabulary',dimension='recognition',evidence_type='recognition')
    items += [evidence(i,0,kind='vocabulary',dimension='production') for i in range(7,10)]
    state = calculate('vocab_taberu','vocabulary',items)
    assert state['dimensions']['recognition']['score'] > .7
    assert state['dimensions']['production']['score'] < .4
    assert state['status'] != 'strong' and .3 < state['score'] < .7


def test_synthetic_b_strong_varied_grammar_and_minimum_safeguard():
    states = [calculate('tai_form','grammar',varied(n)) for n in (1,4,20,80)]
    assert all(s['status']!='strong' for s in states[:2])
    assert states[-1]['status']=='strong' and states[-1]['confidence']>.65
    assert states[-1]['score']>.85


def test_synthetic_c_forgotten_grammar_gradual_decline():
    items = varied(80)
    before = calculate('tai_form','grammar',items)
    states = []
    for i in range(80,84):
        items.append(evidence(i,0))
        states.append(calculate('tai_form','grammar',items))
    assert states[0]['score'] >= before['score']-.081
    assert states[-1]['score'] > .65 and states[-1]['status']=='needs_review'


def test_synthetic_d_kanji_reading_unevenness_and_unknown_production():
    items=[]
    for index,(dimension,score) in enumerate([('recognition',1),('meaning',1),('on_reading',.65),('kun_reading',.1)]):
        items += [evidence(index*20+i,score,kind='kanji',dimension=dimension,reading_context='学生') for i in range(20)]
    state=calculate('kanji_gaku','kanji',items)
    assert state['dimensions']['production']['score'] is None
    assert state['dimensions']['recognition']['score']>.85
    assert state['dimensions']['kun_reading']['score']<.25
    assert state['score'] < .7 and state['status']!='strong'


def raw_event(**changes):
    values=dict(event_id='event', learner_id='learner', event_type='performance', topic_key='vocab_taberu',
        skill='vocabulary',score=1,difficulty=2,source='curriculum',created_at=START.isoformat())
    values.update(changes)
    return values


@pytest.mark.parametrize('patch', [{'score':-1},{'score':1.1},{'score':float('nan')}, {'topic_key':'unknown'},
    {'event_type':'requested_help','score':None}])
def test_normalizer_rejects_invalid_or_unscored_evidence(patch):
    assert normalize(raw_event(**patch),{}) == []


def test_invalid_dimension_and_answer_reveal_are_not_positive_evidence():
    assert normalize(raw_event(),{'mastery':{'dimension':'on_reading'}})==[]
    assert normalize(raw_event(),{'mastery':{'dimension':'production','answer_revealed':True}})==[]
    assert normalize(raw_event(),{'mastery':{'dimension':'invented'}})==[]


def test_kanji_readings_require_context_and_do_not_leak_across_items():
    row = raw_event(topic_key='kanji_gaku_reading',skill='kanji')
    assert normalize(row,{'mastery':{'dimension':'on_reading'}})==[]
    item = normalize(row,{'mastery':{'dimension':'on_reading','reading_context':'学生'}})[0]
    assert item.topic_id=='kanji_gaku' and item.dimension=='on_reading'
    word = normalize(raw_event(topic_key='vocab_gakkou'),{'mastery':{'dimension':'reading'}})
    assert len(word)==1 and word[0].topic_id=='vocab_gakkou'


def test_placement_low_confidence_and_recognition_caps():
    state = measure(series(80, source='placement_assessment'))
    assert state['confidence'] <= .35 and state['status']!='strong'
    assert measure(series(80,evidence_type='recognition'))['confidence']<=.45


def add_event(client, learner, index, *, key='tai_form', score=1, dimension='production', context=None, metadata=None):
    event = LearningEvent(event_id=uuid4(),learner_id=learner,event_type='performance',topic_key=key,
        skill='grammar',score=score,source='manual_review')
    info = metadata if metadata is not None else {'mastery':{'dimension':dimension,'evidence_type':'production',
        'activity_type':'sentence_construction','context_id':context or f'question-{index}','hint_used':False}}
    with client.app.state.learners.repository.connection() as db:
        db.execute('BEGIN IMMEDIATE')
        process_event(db,event,metadata_extra=info)
    return event


def test_persistence_duplicates_recompute_history_and_restart(client,settings,provider):
    learner=create(client)
    last=None
    for i in range(12): last=add_event(client,learner,i)
    service=client.app.state.mastery
    before=service.get_topic_mastery(learner,'tai_form')
    history=service.get_recent_mastery_changes(learner,'tai_form')
    with service.repository.connection() as db:
        assert process_event(db,last) is False
        assert not process_stored_event(db,last.event_id)
    assert service.get_topic_mastery(learner,'tai_form')==before
    assert before['algorithm_version']==VERSION and before['evidence_count']==12
    assert 1 <= len(history) < 12
    service.recalculate_mastery(learner)
    assert service.get_topic_mastery(learner,'tai_form')==before
    assert service.get_recent_mastery_changes(learner,'tai_form')==history
    with TestClient(create_app(settings,provider)) as other:
        assert other.app.state.mastery.get_topic_mastery(learner,'tai_form')==before


def test_mastery_failure_rolls_back_learning_event(client):
    learner=create(client)
    with client.app.state.learners.repository.connection() as db:
        db.execute("CREATE TRIGGER fail_mastery BEFORE INSERT ON topic_mastery BEGIN SELECT RAISE(ABORT,'test'); END")
    with pytest.raises(Exception): add_event(client,learner,0)
    with client.app.state.learners.repository.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM learning_events WHERE learner_id=?',(learner,)).fetchone()[0]==0
        assert db.execute('SELECT COUNT(*) FROM mastery_evidence').fetchone()[0]==0


def test_api_scoping_filters_unknowns_and_zero_llm_calls(client,provider):
    learner,other=create(client),create(client)
    add_event(client,learner,0)
    root=f'/api/learners/{learner}/mastery'
    data=client.get(root+'?type=grammar').json()
    assert all(s['topic_type']=='grammar' for s in data['items'])
    assert client.get(root+'/tai_form').json()['evidence_count']==1
    assert client.get(f'/api/learners/{other}/mastery/tai_form').json()['score'] is None
    assert client.get(f'/api/learners/{uuid4()}/mastery').status_code==404
    assert client.get(root+'/invented').status_code==404
    assert client.get(root+'?type=listening').status_code==422
    assert client.get(root+'?limit=101').status_code==422
    assert not provider.calls


def test_curriculum_records_item_dimension_before_atomic_mastery_update(client):
    learner=create(client)
    plan=plan_api(client,learner,available_minutes=5,session_type='vocabulary')
    activity,url=activate(client,learner,plan)
    client.post(url+'/open')
    from app.curriculum.catalog import CATALOG
    from app.mastery.catalog import curriculum_key
    body={'submission_id':str(uuid4()),'answer':CATALOG[activity['topic_id']].answer}
    assert client.post(url+'/complete',json=body).status_code==200
    assert client.post(url+'/complete',json=body).status_code==200
    state=client.app.state.mastery.get_topic_mastery(learner,curriculum_key(activity['topic_id']))
    assert state['evidence_count']==1 and state['dimensions']['meaning']['evidence_count']==1
    assert state['dimensions']['recognition']['evidence_count']==1
    assert state['dimensions']['production']['score'] is None


def test_phase_three_explicit_correction_production(client,provider):
    from tests.conftest import sample_response
    learner=create(client)
    provider.raw=json.dumps({**sample_response(),'learning_observations':[{
        'event_type':'performance','skill':'grammar','topic_key':'particle_ni','score':.25,'difficulty':2,'error_tags':['particle_ni']}]})
    body=saved_request(client,learner); body['mode']='correct'
    assert client.post('/api/chat',json=body).status_code==200
    state=client.app.state.mastery.get_topic_mastery(learner,'particle_ni_destination')
    assert state['dimensions']['production']['evidence_count']==1
    assert state['confidence']<.1


def test_curriculum_mastery_signal_focus_and_fallback(client):
    data=mature(client)
    before=ranks(data,session_type='grammar')
    key='verb_forms'
    mastery=calculate(key,'grammar',series(8,score=0))
    data['mastery']={key:mastery}
    after=ranks(data,session_type='grammar')
    assert after[key]['focus_dimension']=='production'
    assert after[key]['activity_type']=='sentence_construction'
    assert after[key]['priority']>before[key]['priority']
    data['mastery']={}
    assert ranks(data,session_type='grammar')==before


def test_fixed_vocabulary_focus_generates_recall_without_provider(client,provider):
    learner=create(client)
    from app.curriculum.content import ContentService
    import asyncio
    activity=dict(topic_id='vocab_food',difficulty=1,focus_dimension='production')
    lesson=asyncio.run(ContentService(provider,45).generate(activity,profile(client,learner)))
    assert lesson.choices==[] and lesson.answers==['水','みず']
    assert '水' not in lesson.prompt and not provider.calls


def test_v3_migration_preserves_every_original_row_and_backfills(settings,provider):
    with TestClient(create_app(settings,provider)) as c:
        learner=create(c); add_event(c,learner,0)
    with sqlite3.connect(settings.assessment_db_path) as db:
        for name in ('mastery_history','topic_mastery','mastery_evidence'): db.execute(f'DROP TABLE {name}')
        db.execute('PRAGMA user_version=3')
        tables=['learner_state','learner_topics','learning_events','learner_profiles','study_sessions','study_activities']
        original={t:db.execute(f'SELECT * FROM {t}').fetchall() for t in tables}
    for _ in range(2):
        with TestClient(create_app(settings,provider)) as c:
            assert c.app.state.mastery.get_topic_mastery(learner,'tai_form')['evidence_count']==1
        with sqlite3.connect(settings.assessment_db_path) as db:
            assert db.execute('PRAGMA user_version').fetchone()[0]==8
            assert {t:db.execute(f'SELECT * FROM {t}').fetchall() for t in tables}==original


def test_failed_mastery_migration_rolls_back(settings,provider,monkeypatch):
    with TestClient(create_app(settings,provider)) as c: create(c)
    with sqlite3.connect(settings.assessment_db_path) as db:
        for name in ('mastery_history','topic_mastery','mastery_evidence'): db.execute(f'DROP TABLE {name}')
        db.execute('PRAGMA user_version=3')
    from app.mastery import migrations
    monkeypatch.setattr(migrations,'DDL',migrations.DDL+['INVALID SQL'])
    with TestClient(create_app(settings,provider)) as c:
        assert not c.app.state.learners.repository.ready
    with sqlite3.connect(settings.assessment_db_path) as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==3
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='topic_mastery'").fetchone()


def test_placement_initialization_seeds_limited_mastery(client):
    from tests.test_assessment import start, skip
    from app.learner.initialization import initialize_placement
    from app.assessment.schemas import LearnerProfile
    result=start(client)
    for _ in range(4): result=skip(client,result).json()
    baseline=LearnerProfile.model_validate(result['result']).model_copy(update={'learner_id':uuid4(),'assessment_id':uuid4()})
    state={'evidence':[{'question':{'id':'test-placement','topic':'tai_form','skill':'grammar',
        'difficulty':2,'prompt':'Select the form meaning want to eat.','question_type':'grammar_selection','evaluation':'choice'},
        'evaluation':{'score':1}}]}
    with client.app.state.learners.repository.connection() as db:
        initialize_placement(db,baseline.model_dump_json(),json.dumps(state))
    mastery=client.app.state.mastery.get_topic_mastery(baseline.learner_id,'tai_form')
    assert mastery['evidence_count']==1 and mastery['confidence']<=.35
    assert mastery['dimensions']['production']['score'] is None


def test_unknown_legacy_metadata_never_claims_production_or_strong(client):
    learner=create(client)
    for i in range(12): add_event(client,learner,i,metadata={})
    state=client.app.state.mastery.get_topic_mastery(learner,'tai_form')
    assert state['dimensions']['production']['score'] is None
    assert state['confidence'] < .1 and state['status']!='strong'


def test_dual_dimension_recompute_matches_runtime(client):
    learner=create(client)
    for i in range(8):
        add_event(client,learner,i,key='vocab_taberu',metadata={'mastery':{
            'dimension':'meaning','evidence_type':'recognition','context_id':f'question{i}'}})
    service=client.app.state.mastery
    before=service.get_topic_mastery(learner,'vocab_taberu')
    history=service.get_recent_mastery_changes(learner,'vocab_taberu')
    service.recalculate_mastery(learner)
    assert service.get_topic_mastery(learner,'vocab_taberu')==before
    assert service.get_recent_mastery_changes(learner,'vocab_taberu')==history
    assert before['evidence_count']==8


def test_recompute_stable_under_input_permutation():
    items=varied(40)
    assert calculate('tai_form','grammar',items)==calculate('tai_form','grammar',list(reversed(items)))


def test_each_new_evidence_has_bounded_overall_change_even_new_dimension():
    items=series(30,dimension='recognition')
    old=calculate('tai_form','grammar',items)['score']
    for dimension in ('production','application','understanding'):
        items.append(evidence(len(items),0,dimension=dimension))
        new=calculate('tai_form','grammar',items)['score']
        assert abs(new-old)<=.081
        old=new


def test_exposure_and_unknown_tag_do_not_score(client):
    learner=create(client)
    event=LearningEvent(event_id=uuid4(),learner_id=learner,event_type='concept_explained',
        topic_key='tai_form',skill='grammar',source='tutor_chat')
    client.app.state.learners.record(event)
    add_event(client,learner,0,key='unbounded_new_tag')
    assert client.app.state.mastery.get_topic_mastery(learner,'tai_form')['score'] is None


def test_reading_and_production_curriculum_gaps_are_separate(client):
    data=mature(client)
    key='vocab_mizu'
    data['mastery']={key:calculate(key,'vocabulary',series(8,score=0,kind='vocabulary',dimension='reading'))}
    candidate=ranks(data,session_type='vocabulary')['vocab_food']
    assert candidate['focus_dimension']=='reading'


def test_local_reset_removes_mastery_for_one_learner_only(client):
    from app.learner.reset import reset_learner
    learner,other=create(client),create(client)
    add_event(client,learner,0); add_event(client,other,0)
    reset_learner(client.app.state.learners.repository,learner,learner)
    assert client.app.state.mastery.get_topic_mastery(learner,'tai_form')['score'] is None
    assert client.app.state.mastery.get_topic_mastery(other,'tai_form')['evidence_count']==1


def test_future_interfaces_and_history_bound(client):
    learner=create(client)
    for i in range(3): add_event(client,learner,i)
    service=client.app.state.mastery
    assert 'production' in service.get_mastery_dimensions(learner,'tai_form')
    assert service.get_low_confidence_topics(learner)
    assert service.get_topics_needing_review(learner)==[]
    assert service.get_topic_last_seen(learner,'tai_form')
    assert len(service.get_recent_mastery_changes(learner,limit=1))==1
