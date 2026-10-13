"""Phase 12C isolated fixtures: no live user, provider, email or learner writes."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
import json
from uuid import UUID,uuid4

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.accounts import COOKIE,IDLE,ABSOLUTE
from app.account_link_migration import migrate,present
from app.auth import AuthenticationError
from app.main import create_app
from app.learner_access import AccessScope,scope
from tests.test_accounts import Authority,enabled,bootstrap,signin,PASSWORD,FRONTEND
from tests.test_staging import CODE,SIGNING,login as gate_login
from app.accounts import SupabaseAccounts
from tests.test_postgres import pg_settings
import psycopg

@pytest.fixture
def linked_context(request,settings,provider):
    mode = getattr(request, 'param', 'sqlite')
    if mode.startswith('postgres'):
        settings = request.getfixturevalue('pg_settings')
    authority=Authority();enabled(settings,authority)
    settings.account_owner_bootstrap_ids=SecretStr(authority.payload['sub'])
    settings.staging_access_enabled=True;settings.scope_enforcement_enabled=True
    settings.staging_access_code=SecretStr(CODE);settings.staging_session_secret=SecretStr(SIGNING)
    adapter=SupabaseAccounts(settings,httpx.MockTransport(authority.handle))
    if settings.database_url.get_secret_value():
        # This fixture receives only the loopback-only disposable database from
        # pg_settings. Never create provider tables in an actual Supabase project.
        with psycopg.connect(settings.database_url.get_secret_value()) as db:
            db.execute('CREATE SCHEMA auth')
            db.execute('CREATE TABLE auth.users (id UUID PRIMARY KEY)')
            db.execute('CREATE TABLE auth.sessions (id UUID PRIMARY KEY,user_id UUID REFERENCES auth.users(id))')
            for payload in (authority.payload,authority.second):
                db.execute('INSERT INTO auth.users VALUES (%s)',(payload['sub'],))
                db.execute('INSERT INTO auth.sessions VALUES (%s,%s)',(payload['session_id'],payload['sub']))
    app=create_app(settings,provider,account_provider=adapter)
    with TestClient(app,base_url=FRONTEND) as client:
        client.authority=authority;gate_login(client)
        if mode.endswith('history'):
            from tests.test_assessment import start,skip
            state=start(client)
            while state['status']!='completed':state=skip(client,state).json()
            learner=state['learner_id']
        else:
            learner=client.post('/api/learners').json()['learner_id']
        migrate(app.state.repository);settings.account_learner_linking_enabled=True
        yield client,learner,authority

def login(client,email='test@example.test'):
    result=client.post('/api/account/login',json={'email':email,'password':PASSWORD},headers=bootstrap(client));assert result.status_code==200,result.text
    return bootstrap(client)

def preview(client):
    result=client.get('/api/account/link-preview');assert result.status_code==200,result.text
    return result.json()['confirmation']

def confirm(client,proof):
    return client.post('/api/account/link-learner',json={'confirm':True,'confirmation':proof},headers=bootstrap(client))

def table_snapshot(repo):
    with repo.connection() as db:
        query = "SELECT table_name FROM information_schema.tables WHERE table_schema='tutor_private' ORDER BY table_name" if repo.database_url else "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        names=[r[0] for r in db.execute(query).fetchall() if not r[0].startswith('sqlite_') and r[0] not in ('account_sessions','account_learner_links')]
        return {name:sorted(db.execute('SELECT * FROM '+name).fetchall(),key=repr) for name in names}

def test_explicit_owner_link_preserves_all_data_and_is_idempotent(linked_context):
    client,learner,_=linked_context;repo=client.app.state.repository
    # Seed actual session/preferences through their legacy-authorized interfaces.
    session=client.post(f'/api/learners/{learner}/sessions').json()['session_id']
    assert client.patch(f'/api/learners/{learner}/preferences',json={'primary_goal':'conversation'}).status_code==200
    before=table_snapshot(repo);login(client)
    assert client.get('/api/account/learner').json()['state']=='unlinked'
    proof=preview(client)
    assert table_snapshot(repo)==before
    with repo.connection() as db:assert db.execute('SELECT count(*) FROM account_learner_links').fetchone()[0]==0
    response=confirm(client,proof);assert response.status_code==200,response.text
    assert confirm(client,proof).status_code==200
    assert client.get('/api/account/learner').json()['learner_id']==learner
    assert client.get('/api/account/me').json()['profile']=='linked'
    assert client.get(f'/api/learners/{learner}/profile').status_code==200
    assert client.get(f'/api/learners/{learner}/sessions/{session}').status_code==200
    assert table_snapshot(repo)==before
    with repo.connection() as db:
        row=db.execute('SELECT * FROM account_learner_links').fetchall();assert len(row)==1
        assert row[0][1]==learner and row[0][3]==1 and row[0][4]=='signed_legacy_owner_v1'
        assert row[0][5] not in (learner,client.authority.payload['sub'])

@pytest.mark.parametrize('body',[{}, {'confirm':False}, {'confirm':1}, {'confirm':True,'learner_id':'arbitrary'}, {'confirm':True,'account_id':'arbitrary'}])
def test_no_implicit_or_browser_id_claim(linked_context,body):
    client,_,_=linked_context;login(client);proof=preview(client)
    result=client.post('/api/account/link-learner',json={'confirmation':proof,**body},headers=bootstrap(client))
    assert result.status_code==422
    with client.app.state.repository.connection() as db:assert db.execute('SELECT count(*) FROM account_learner_links').fetchone()[0]==0

@pytest.mark.parametrize('failure',['signed-out','expired','unconfirmed','policy','signature'])
def test_invalid_account_cannot_preview_or_confirm(linked_context,failure):
    client,_,authority=linked_context;login(client);proof=preview(client);headers=bootstrap(client)
    if failure=='signed-out':client.post('/api/account/logout',json={},headers=headers)
    elif failure=='expired':client.app.state.accounts.clock=lambda:10**12
    elif failure=='unconfirmed':authority.user.pop('email_confirmed_at')
    elif failure=='policy':authority.public=True
    elif failure=='signature':authority.bad='signature'
    assert client.get('/api/account/link-preview').status_code in (401,503)
    assert client.post('/api/account/link-learner',json={'confirm':True,'confirmation':proof},headers=headers).status_code in (401,403,503)

@pytest.mark.parametrize('missing',['lost-legacy','multiple','no-learner','learner-removed'])
def test_legacy_context_must_be_unambiguous_and_unchanged(linked_context,missing):
    client,learner,_=linked_context;repo=client.app.state.repository
    if missing=='multiple':assert client.post('/api/learners').status_code==201
    if missing=='no-learner':
        with repo.connection() as db:db.execute("DELETE FROM staging_resources WHERE kind='learner' AND resource_id=?",(learner,))
    login(client)
    if missing=='lost-legacy':
        # Another legitimate gate cookie is not ownership of the original profile.
        with TestClient(client.app,base_url=FRONTEND) as other:
            other.authority=client.authority;gate_login(other);login(other)
            assert other.get('/api/account/link-preview').status_code==409
        return
    if missing=='learner-removed':
        proof=preview(client)
        with repo.connection() as db:db.execute("DELETE FROM staging_resources WHERE kind='learner' AND resource_id=?",(learner,))
        assert confirm(client,proof).status_code==409
    else:assert client.get('/api/account/link-preview').status_code==409

@pytest.mark.parametrize('failure',['csrf','origin','cross-site','false-confirm','tampered','old-proof','stale-auth'])
def test_confirmation_security_boundaries(linked_context,failure):
    client,_,_=linked_context;login(client);proof=preview(client);headers=bootstrap(client)
    now=client.app.state.accounts.clock()
    if failure=='csrf':headers['X-CSRF-Token']='wrong'
    elif failure=='origin':headers['Origin']='https://foreign.test'
    elif failure=='cross-site':headers['Sec-Fetch-Site']='cross-site'
    elif failure=='tampered':proof=proof[:-4]+'xxxx'
    elif failure=='old-proof':client.app.state.accounts.clock=lambda:now+301
    elif failure=='stale-auth':client.app.state.accounts.clock=lambda:now+601
    body={'confirm':failure!='false-confirm','confirmation':proof}
    result=client.post('/api/account/link-learner',json=body,headers=headers)
    assert result.status_code in (401,403,409,422),result.text
    with client.app.state.repository.connection() as db:assert db.execute('SELECT count(*) FROM account_learner_links').fetchone()[0]==0

def test_same_account_second_client_restores_without_shared_browser_state(linked_context):
    client,learner,_=linked_context;login(client);assert confirm(client,preview(client)).status_code==200
    with TestClient(client.app,base_url=FRONTEND) as other:
        other.authority=client.authority;gate_login(other);login(other)
        assert other.get('/api/account/learner').json()['learner_id']==learner
        assert other.get(f'/api/learners/{learner}/profile').json()['learner_id']==learner
        assert other.get(f'/api/learners/{learner}/sessions').status_code==200
        # Current-browser logout does not revoke the other application session.
        assert other.post('/api/account/logout',json={},headers=bootstrap(other)).status_code==200
        assert other.get(f'/api/learners/{learner}/profile').status_code==401
        assert client.get(f'/api/learners/{learner}/profile').status_code==200

def test_other_account_or_original_legacy_cookie_cannot_read_linked_history(linked_context):
    client,learner,authority=linked_context;login(client);assert confirm(client,preview(client)).status_code==200
    with TestClient(client.app,base_url=FRONTEND) as other:
        other.authority=authority;gate_login(other)
        authority.payload=authority.second;authority.active=authority.payload;authority.user={'id':authority.payload['sub'],'email':'other@example.test','email_confirmed_at':'2026-01-01T00:00:00Z','invited_at':'2026-01-01T00:00:00Z','is_anonymous':False}
        with client.app.state.repository.connection() as db:db.execute('INSERT INTO account_beta_members VALUES (?,?)',(authority.payload['sub'],0))
        login(other,'other@example.test')
        assert other.get('/api/account/learner').json()['state']=='unlinked'
        assert other.get(f'/api/learners/{learner}/profile').status_code==401
        assert other.get('/api/account/link-preview').status_code==401
        assert other.post('/api/account/link-learner',json={'confirm':True,'confirmation':'arbitrary'},headers=bootstrap(other)).status_code in (401,422)
    # The original signed staging capability ceases to authorize linked records.
    client.cookies.delete(COOKIE)
    assert client.get(f'/api/learners/{learner}/profile').status_code==401

def test_linking_requires_fresh_auth_and_owner_exception_never_auto_links(linked_context):
    client,_,_=linked_context;login(client)
    with client.app.state.repository.connection() as db:assert db.execute('SELECT count(*) FROM account_learner_links').fetchone()[0]==0
    now=client.app.state.accounts.clock();client.app.state.accounts.clock=lambda:now+601
    assert client.get('/api/account/link-preview').status_code==401

def test_replay_from_different_account_session_is_rejected(linked_context):
    client,_,_=linked_context;login(client);proof=preview(client);login(client)
    assert confirm(client,proof).status_code==401

def test_authenticated_profile_creation_and_replacement_placement_are_deferred(linked_context):
    client,_,_=linked_context;login(client)
    for path,body in [('/api/learners',None),('/api/assessments',{'self_report':'beginner'})]:
        result=client.post(path,json=body);assert result.status_code==409,result.text
    with client.app.state.repository.connection() as db:assert db.execute('SELECT count(*) FROM learner_state').fetchone()[0]==1

def test_concurrent_identical_link_creates_one_association(linked_context):
    client,_,_=linked_context;login(client);proof=preview(client)
    from app.api.accounts import owner,nonce
    # Exercise the actual locked service using the authenticated fixture cookie.
    value=client.cookies.get(COOKIE)
    with client.app.state.repository.connection() as db:legacy_owner=db.execute('SELECT staging_owner FROM account_sessions WHERE purpose=?',('ready',)).fetchone()[0]
    with ThreadPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(lambda _:client.app.state.account_links.confirm(value,legacy_owner,proof),range(4)))
    assert all(r['state']=='linked' for r in results)
    with client.app.state.repository.connection() as db:assert db.execute('SELECT count(*) FROM account_learner_links').fetchone()[0]==1

def test_link_ownership_is_rechecked_inside_learning_transaction(linked_context):
    client,learner,_=linked_context;login(client);proof=preview(client)
    # A legacy authorization snapshot taken just before ownership changes cannot
    # be used afterward by a delayed service write.
    with client.app.state.repository.connection() as db:legacy_owner=db.execute("SELECT owner_id FROM staging_resources WHERE kind='learner' AND resource_id=?",(learner,)).fetchone()[0]
    assert confirm(client,proof).status_code==200
    token=scope.set(AccessScope(legacy_owner,None,(('learner',learner),)))
    try:
        with pytest.raises(Exception) as error:
            with client.app.state.repository.connection() as db:db.execute("UPDATE learner_state SET estimated_level='changed' WHERE learner_id=?",(learner,))
        assert getattr(error.value,'status',None)==401
    finally:scope.reset(token)
    assert client.get(f'/api/learners/{learner}/profile').json()['estimated_level']=='Beginner'

def test_disabled_new_linking_preserves_existing_account_ownership(linked_context):
    client,learner,_=linked_context;login(client);assert confirm(client,preview(client)).status_code==200
    client.app.state.settings.account_learner_linking_enabled=False
    assert client.get('/api/account/learner').json()['learner_id']==learner
    assert client.get('/api/account/link-preview').status_code==503
    client.cookies.delete(COOKIE)
    assert client.get(f'/api/learners/{learner}/profile').status_code==401

def test_migration_is_additive_idempotent_and_restricts_learner_deletion(linked_context):
    client,learner,_=linked_context;repo=client.app.state.repository;before=table_snapshot(repo)
    migrate(repo);assert table_snapshot(repo)==before
    login(client);assert confirm(client,preview(client)).status_code==200
    with pytest.raises(Exception):
        with repo.connection() as db:db.execute('DELETE FROM learner_state WHERE learner_id=?',(learner,))
    assert table_snapshot(repo)==before


@pytest.mark.parametrize('linked_context',['postgres'],indirect=True)
def test_postgres_concurrency_and_independent_restore(linked_context):
    test_concurrent_identical_link_creates_one_association(linked_context)


@pytest.mark.parametrize('linked_context',['sqlite-history','postgres-history'],indirect=True)
def test_full_history_is_unchanged_by_link_and_restore(linked_context,monkeypatch):
    from tests.test_reviews import Clock,record
    from tests.test_flashcard_reviews import due,submit
    from tests.test_curriculum import plan_api
    from tests.test_conversation import start as conversation_start,body
    from tests.test_jlpt import start as jlpt_start,submit as jlpt_submit
    from tests.test_audio_progress import attempt,complete
    from tests.test_speech import FakeSpeech,upload
    from app.audio_progress.service import CATALOG
    from app.speech.service import SpeechService
    client,learner,authority=linked_context;repo=client.app.state.repository
    clock=Clock();monkeypatch.setattr('app.learner.events.now_iso',lambda:clock.now().isoformat())
    client.app.state.reviews.clock=clock
    client.app.state.curriculum.reviews.clock=clock
    assert client.patch(f'/api/learners/{learner}/preferences',json={'primary_goal':'conversation','romaji_enabled':True}).status_code==200
    for topic,dim in [('vocab_taberu','meaning'),('tai_form','understanding'),('kanji_gaku','meaning')]:record(client,learner,topic,dim)
    item=due(client,learner,clock)
    assert submit(client,learner,item)[0].status_code==200
    plan_api(client,learner,available_minutes=10)
    conversation=conversation_start(client,learner).json()
    assert client.post('/api/chat',json=body(learner,conversation,message='こんにちは。')).status_code==200
    jlpt=jlpt_start(client,learner).json();assert jlpt_submit(client,learner,jlpt)[0].status_code==200
    assert client.post(f'/api/learners/{learner}/jlpt/sessions/{jlpt["session_id"]}/finish').status_code==200
    listening=CATALOG['listening'][0];key=attempt(client,learner,listening['id'])
    assert complete(client,learner,key,choice=listening['answer']).status_code==200
    client.app.state.settings.stt_enabled=True;client.app.state.settings.groq_api_key=SecretStr('offline-test-placeholder')
    client.app.state.speech=SpeechService(client.app.state.settings,FakeSpeech())
    speaking=CATALOG['speaking'][0];key=attempt(client,learner,speaking['id'])
    receipt=upload(client,learner).json()['request_id']
    assert complete(client,learner,key,transcription_id=receipt).status_code==200
    before=table_snapshot(repo)
    # All preservation categories contain actual rows, not just empty tables.
    for name in ['assessments','assessment_answers','learner_profiles','learner_state','study_sessions','tutor_sessions','conversation_turns','conversation_states','topic_mastery','mastery_evidence','review_schedules','review_attempts','jlpt_sessions','learning_events']:
        assert before.get(name),name
    types={r[2] for r in before['learning_events']}
    assert {'flashcard_review_completed','listening_unassisted','speaking_completed'} <= types
    login(client);proof=preview(client);assert confirm(client,proof).status_code==200
    with TestClient(client.app,base_url=FRONTEND) as other:
        other.authority=authority;gate_login(other);login(other)
        assert other.get('/api/account/learner').json()['learner_id']==learner
        for suffix in ['profile','activity','sessions','study/active','conversations/active','reviews/due','reviews/history','jlpt/sessions/active','audio/progress']:
            result=other.get(f'/api/learners/{learner}/{suffix}');assert result.status_code==200,(suffix,result.text)
    assert table_snapshot(repo)==before
    if repo.database_url:
        with pytest.raises(Exception):
            with repo.connection() as db:
                db.execute('DELETE FROM auth.sessions WHERE user_id=?',(authority.payload['sub'],))
                db.execute('DELETE FROM auth.users WHERE id=?',(authority.payload['sub'],))
        assert table_snapshot(repo)==before


def test_failed_link_insert_rolls_back_and_can_retry(linked_context,monkeypatch):
    from app.storage import SQLiteConnection
    client,_,_=linked_context;login(client);proof=preview(client);original=SQLiteConnection.execute
    def fail(self,sql,params=()):
        if sql.startswith('INSERT INTO account_learner_links'):
            import sqlite3
            raise sqlite3.OperationalError('fixture-only failure')
        return original(self,sql,params)
    monkeypatch.setattr(SQLiteConnection,'execute',fail)
    assert confirm(client,proof).status_code==503
    with client.app.state.repository.connection() as db:assert db.execute('SELECT count(*) FROM account_learner_links').fetchone()[0]==0
    monkeypatch.setattr(SQLiteConnection,'execute',original)
    assert confirm(client,proof).status_code==200


def test_linked_account_cannot_fallback_to_other_legacy_profile_when_rollout_off(linked_context):
    client,learner,_=linked_context;login(client);assert confirm(client,preview(client)).status_code==200
    settings=client.app.state.settings;settings.account_learner_linking_enabled=False
    # A second legacy profile owned by the same old staging cookie is still not
    # an account-owned resource. Seed via service, not an account creation route.
    second=client.app.state.learners.create()['learner_id']
    with client.app.state.repository.connection() as db:
        old=db.execute("SELECT owner_id FROM staging_resources WHERE kind='learner' AND resource_id=?",(learner,)).fetchone()[0]
        db.execute('INSERT INTO staging_resources VALUES (?,?,?)',('learner',second,old))
    assert client.get(f'/api/learners/{second}/profile').status_code==409


@pytest.mark.parametrize('route',['profile','activity','mastery','reviews/due','reviews/history','jlpt/sessions/active','audio/progress','conversations/active','study/active'])
def test_linked_descendants_reject_legacy_only_access(linked_context,route):
    client,learner,_=linked_context;login(client);assert confirm(client,preview(client)).status_code==200;client.cookies.delete(COOKIE)
    result=client.get(f'/api/learners/{learner}/{route}');assert result.status_code==401,result.text


def test_linked_saved_session_and_upload_check_account_before_use(linked_context):
    from tests.test_speech import upload
    client,learner,_=linked_context
    session=client.post(f'/api/learners/{learner}/sessions').json()['session_id']
    login(client);assert confirm(client,preview(client)).status_code==200;client.cookies.delete(COOKIE)
    assert client.post('/api/chat',json={'session_id':session,'message':'こんにちは。'}).status_code==401
    assert client.delete(f'/api/sessions/{session}').status_code==401
    assert client.post('/api/curriculum/plan',json={'learner_id':learner}).status_code==401
    assert upload(client,learner).status_code==401


@pytest.mark.parametrize('linked_context',['postgres'],indirect=True)
def test_postgres_independent_sessions_restore(linked_context):
    test_same_account_second_client_restores_without_shared_browser_state(linked_context)


@pytest.mark.parametrize('conflict',['account','learner'])
def test_conflicting_ownership_is_not_overwritten(linked_context,conflict):
    client,learner,authority=linked_context;login(client);proof=preview(client);repo=client.app.state.repository
    account=authority.payload['sub']
    if conflict=='account':target=client.app.state.learners.create()['learner_id']
    else:target=learner;account=authority.second['sub']
    with repo.connection() as db:db.execute('INSERT INTO account_learner_links VALUES (?,?,?,?,?,?,?,?)',(account,target,0,1,'signed_legacy_owner_v1','fixture','fixture','fixture'))
    with repo.connection() as db:before=db.execute('SELECT * FROM account_learner_links').fetchall()
    assert confirm(client,proof).status_code==409
    with repo.connection() as db:assert db.execute('SELECT * FROM account_learner_links').fetchall()==before


def test_expired_legacy_capability_does_not_link(linked_context,monkeypatch):
    import app.safeguards as guards
    client,_,_=linked_context;login(client);proof=preview(client);headers=bootstrap(client)
    monkeypatch.setattr(guards,'read_session',lambda *args,**kwargs:None)
    assert client.get('/api/account/link-preview').status_code==401
    assert client.post('/api/account/link-learner',json={'confirm':True,'confirmation':proof},headers=headers).status_code==401
    with client.app.state.repository.connection() as db:assert db.execute('SELECT count(*) FROM account_learner_links').fetchone()[0]==0


def test_migration_never_runs_at_application_startup(settings,provider):
    authority=Authority();enabled(settings,authority)
    with TestClient(create_app(settings,provider,account_provider=SupabaseAccounts(settings,httpx.MockTransport(authority.handle)))) as client:
        with client.app.state.repository.connection() as db:assert not present(db)
    settings.account_owner_bootstrap_ids=SecretStr(authority.payload['sub']);settings.account_learner_linking_enabled=True
    with pytest.raises(RuntimeError,match='separately approved'):
        with TestClient(create_app(settings,provider,account_provider=SupabaseAccounts(settings,httpx.MockTransport(authority.handle)))):pass


@pytest.mark.parametrize('linked_context',['postgres'],indirect=True)
def test_postgres_constraint_failure_and_repeat_migration_are_atomic(linked_context):
    client,learner,authority=linked_context;repo=client.app.state.repository;before=table_snapshot(repo)
    migrate(repo);assert table_snapshot(repo)==before
    for account,target in [(str(uuid4()),learner),(authority.payload['sub'],str(uuid4())),(None,learner)]:
        with pytest.raises(Exception):
            with repo.connection() as db:db.execute('INSERT INTO account_learner_links VALUES (?,?,?,?,?,?,?,?)',(account,target,0,1,'signed_legacy_owner_v1','fixture','fixture','fixture'))
    with repo.connection() as db:assert db.execute('SELECT count(*) FROM account_learner_links').fetchone()[0]==0
    assert table_snapshot(repo)==before


def test_migration_cli_plan_cannot_connect_or_apply_without_checkpoint(monkeypatch,capsys):
    from scripts import migrate_account_links as cli
    monkeypatch.setattr('sys.argv',['migrate_account_links.py'])
    monkeypatch.setattr(cli,'Settings',lambda:(_ for _ in ()).throw(AssertionError('Planning must not load private configuration')))
    assert cli.main()==0;assert 'REFERENCES auth.users(id)' in capsys.readouterr().out
    monkeypatch.setattr('sys.argv',['migrate_account_links.py','--apply'])
    with pytest.raises(SystemExit):cli.main()
