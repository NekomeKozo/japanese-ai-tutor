"""Opt-in real PostgreSQL tests. Only disposable loopback databases are allowed."""
import json
import os
from uuid import uuid4

import psycopg
import pytest
from fastapi.testclient import TestClient
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from pydantic import SecretStr

from app.assessment.questions import QuestionBank
from app.assessment.repository import AssessmentRepository
from app.errors import TutorError
from app.main import create_app
from tests import test_assessment as assessment_tests
from tests import test_reviews as review_tests
from tests import test_learning_memory as memory_tests
from tests.test_staging import CODE, SIGNING, login, test_learner_isolation_and_restart as isolation_flow


@pytest.fixture
def pg_settings(settings):
    url = os.environ.get('TEST_POSTGRES_URL')
    if not url:
        pytest.skip('Set TEST_POSTGRES_URL to a disposable local PostgreSQL instance')
    options = conninfo_to_dict(url)
    if options.get('host') not in ('127.0.0.1', 'localhost', '::1'):
        pytest.fail('Integration tests only create databases on loopback hosts')
    database = 'tutor_test_' + uuid4().hex
    with psycopg.connect(url, autocommit=True, connect_timeout=5) as admin:
        admin.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(database)))
    settings.database_url = SecretStr(make_conninfo(url, dbname=database))
    try:
        yield settings
    finally:
        assert database.startswith('tutor_test_') and len(database) == 43
        with psycopg.connect(url, autocommit=True, connect_timeout=5) as admin:
            admin.execute(sql.SQL('DROP DATABASE {} WITH (FORCE)').format(sql.Identifier(database)))


@pytest.fixture
def pg_client(pg_settings, provider):
    with TestClient(create_app(pg_settings, provider)) as client:
        yield client


def test_fresh_repeat_migration_and_rollback(pg_client, pg_settings):
    repo = pg_client.app.state.repository
    with repo.connection() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0] == 8
        count = db.execute('SELECT count(*) FROM assessment_questions').fetchone()[0]
        assert count == len(QuestionBank.load().items)
    repo.initialize(QuestionBank.load())
    with repo.connection() as db:
        assert db.execute('SELECT count(*) FROM assessment_questions').fetchone()[0] == count
        rows = db.execute('SELECT bank_version,id,payload FROM assessment_questions ORDER BY id').fetchall()
        db.execute('DELETE FROM assessment_questions WHERE bank_version=? AND id=?', tuple(rows[0][:2]))
    repo.initialize(QuestionBank.load())
    with repo.connection() as db:
        assert db.execute('SELECT count(*) FROM assessment_questions').fetchone()[0] == count
        assert db.execute('SELECT payload FROM assessment_questions WHERE bank_version=? AND id=?', tuple(rows[0][:2])).fetchone()[0] == rows[0][2]
    with pytest.raises(TutorError):
        with repo.connection() as db:
            db.execute("INSERT INTO assessment_questions VALUES (?,?,?)", ('rollback', 'test', '{}'))
            db.execute('INSERT INTO no_such_table VALUES (?)', ('not saved',))
    with repo.connection() as db:
        assert db.execute('SELECT 1 FROM assessment_questions WHERE bank_version=?', ('rollback',)).fetchone() is None
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name='review_schedules'").fetchone()
    with psycopg.connect(pg_settings.database_url.get_secret_value(), connect_timeout=5) as db:
        assert not db.execute("SELECT 1 FROM information_schema.tables WHERE table_schema='public' AND table_name='learner_state'").fetchone()


def test_flashcard_recall_receipt_and_replay_postgres(pg_client,pg_settings,provider,monkeypatch):
    from tests.test_flashcard_reviews import test_retry_restart_and_stale_version, test_suspension_and_replay_preserve_existing_history
    clock=review_tests.Clock(); learner=memory_tests.create(pg_client)
    monkeypatch.setattr('app.learner.events.now_iso',lambda:clock.now().isoformat())
    pg_client.app.state.reviews.clock=clock
    test_retry_restart_and_stale_version(pg_client,(learner,clock),pg_settings,provider)
    learner=memory_tests.create(pg_client)
    clock.value=review_tests.NOW
    test_suspension_and_replay_preserve_existing_history(pg_client,(learner,clock))


def test_private_knowledge_migration_rebuild_and_rollback(pg_client,pg_settings):
    from app.knowledge.repository import KnowledgeRepository
    from tests.test_knowledge import seed,document
    from app.knowledge.chunker import chunk_document
    repo=KnowledgeRepository(database_url=pg_settings.database_url.get_secret_value())
    repo.initialize(); seed(repo); repo.initialize()
    assert repo.retrieve('destination')[0].chunk.page==1
    before=repo.counts()
    doc=document('destination replacement rollback')
    chunks=chunk_document(doc)
    with pytest.raises(TutorError): repo.replace_source(doc.source,chunks+chunks,'bad')
    assert repo.counts()==before and repo.source_version(doc.source.source_id)=='v1'
    with pg_client.app.state.repository.connection() as db:
        assert db.execute('PRAGMA user_version').fetchone()[0]==8
        assert db.execute('SELECT COUNT(*) FROM assessment_questions').fetchone()[0]>0
        assert db.execute("SELECT table_schema FROM information_schema.tables WHERE table_name='knowledge_chunks'").fetchone()[0]=='tutor_private'


def test_migration_failure_is_atomic(pg_settings, monkeypatch):
    from app.review import migrations
    original = migrations.migrate
    def fail(db):
        raise ValueError('simulated migration failure')
    monkeypatch.setattr(migrations, 'migrate', fail)
    repo = AssessmentRepository('unused', pg_settings.database_url.get_secret_value())
    with pytest.raises(TutorError):
        repo.initialize(QuestionBank.load())
    assert not repo.ready
    with psycopg.connect(pg_settings.database_url.get_secret_value(), connect_timeout=5) as db:
        assert db.execute("SELECT to_regclass('tutor_private.assessments')").fetchone()[0] is None
    monkeypatch.setattr(migrations, 'migrate', original)
    repo.initialize(QuestionBank.load())
    assert repo.ready


def test_placement_preferences_history_restart(pg_client, pg_settings, provider):
    state = assessment_tests.start(pg_client)
    for _ in range(30):
        if state['status'] == 'completed':
            break
        response = assessment_tests.skip(pg_client, state)
        assert response.status_code == 200, response.text
        state = response.json()
    assert state['status'] == 'completed'
    learner = state['learner_id']
    assert pg_client.patch(f'/api/learners/{learner}/preferences', json={'romaji_enabled': True}).status_code == 200
    before = pg_client.get(f'/api/learners/{learner}/profile').json()
    assert before['preferences']['romaji_enabled'] is True
    with TestClient(create_app(pg_settings, provider)) as restarted:
        assert restarted.get(f'/api/learners/{learner}/profile').json() == before
        assert restarted.get(f'/api/assessments/{state["assessment_id"]}/result').status_code == 200
        assert restarted.get(f'/api/learners/{learner}/activity').json()


def test_curriculum_mastery_review_retry_restart(pg_client, pg_settings, provider, monkeypatch):
    clock = review_tests.Clock()
    learner = memory_tests.create(pg_client)
    monkeypatch.setattr('app.learner.events.now_iso', lambda: clock.now().isoformat())
    pg_client.app.state.reviews.clock = clock
    pg_client.app.state.curriculum.reviews.clock = clock
    review_tests.test_full_review_atomic_retry_restart(pg_client, (learner, clock), pg_settings, provider)


def test_access_ownership_persists_on_postgres(pg_settings, provider):
    pg_settings.staging_access_enabled = True
    pg_settings.staging_access_code = SecretStr(CODE)
    pg_settings.staging_session_secret = SecretStr(SIGNING)
    with TestClient(create_app(pg_settings, provider)) as client:
        isolation_flow(client, pg_settings, provider)
