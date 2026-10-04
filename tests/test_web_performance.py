"""Focused asset/privacy and event-loop regressions, with offline disposable data."""
import asyncio
import re
import threading

import httpx
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.main import create_app
from app.web_assets import WebAssets
from app.assessment.questions import QuestionBank
from app.assessment.repository import AssessmentRepository
from app.safeguards import COOKIE, sign_session
from uuid import uuid4


def test_versioned_assets_compress_without_changing_content(client):
    html = client.get('/')
    assert html.headers['cache-control'] == 'no-store'
    version = re.search('data-asset-version="([a-f0-9]+)"', html.text)[1]
    urls = re.findall(r'(?:src|href)="(/static/[^" ]+\.(?:js|css)\?v=[a-f0-9]+)"', html.text)
    assert len(urls) == 20
    for url in urls + ['/static/flashcard-catalog.json?v=' + version]:
        zipped = client.get(url, headers={'Accept-Encoding': 'gzip'})
        plain = client.get(url, headers={'Accept-Encoding': 'identity'})
        assert zipped.content == plain.content
        assert zipped.headers['content-encoding'] == 'gzip'
        assert int(zipped.headers['content-length']) < len(zipped.content)
        assert zipped.headers['cache-control'] == 'private, max-age=31536000, immutable'
        validated = client.get(url, headers={'If-None-Match': zipped.headers['etag']})
        assert validated.status_code == 304
        assert validated.content == b''
    for url in ['/static/app.js', '/static/app.js?v=old']:
        assert client.get(url).headers['cache-control'] == 'private, max-age=0, must-revalidate'
    for url in ['/access', '/api/health', '/static/missing.js?v=' + version]:
        response = client.get(url, headers={'Accept-Encoding': 'gzip'})
        assert response.headers['cache-control'] == 'no-store'
        assert 'content-encoding' not in response.headers


def test_deployment_content_changes_asset_version(tmp_path):
    (tmp_path / 'index.html').write_text('<html lang="en"><script src="/static/app.js"></script>', encoding='utf-8')
    (tmp_path / 'app.js').write_text('first', encoding='utf-8')
    first = WebAssets(tmp_path)
    assert '?v=' + first.version in first.index
    assert WebAssets(tmp_path).version == first.version
    (tmp_path / 'app.js').write_text('changed', encoding='utf-8')
    assert WebAssets(tmp_path).version != first.version


def test_cache_does_not_bypass_access_or_ownership(settings, provider):
    settings.staging_access_enabled = True
    settings.staging_access_code = SecretStr('test-only-access-code')
    settings.staging_session_secret = SecretStr('test-only-signing-secret-at-least-32')
    with TestClient(create_app(settings, provider)) as client:
        client.cookies.set(COOKIE, sign_session(str(uuid4()), settings))
        html = client.get('/').text
        url = re.search(r'src="(/static/app.js\?v=[a-f0-9]+)"', html)[1]
        learner = client.post('/api/learners').json()['learner_id']
        profile = client.get(f'/api/learners/{learner}/profile', headers={'Accept-Encoding': 'gzip'})
        assert profile.status_code == 200
        assert profile.headers['cache-control'] == 'no-store'
        assert 'content-encoding' not in profile.headers
        client.cookies.clear()
        response = client.get(url)
        assert response.status_code == 401
        assert response.headers['cache-control'] == 'no-store'
        client.cookies.set(COOKIE, sign_session(str(uuid4()), settings))
        denied = client.get(f'/api/learners/{learner}/profile')
        assert denied.status_code == 404
        assert denied.headers['cache-control'] == 'no-store'
        assert not provider.calls


def test_batched_bank_restores_missing_only(tmp_path):
    repository = AssessmentRepository(str(tmp_path / 'bank.sqlite3'))
    bank = QuestionBank.load()
    repository.initialize(bank)
    with repository.connection() as db:
        rows = db.execute('SELECT id,payload FROM assessment_questions ORDER BY id').fetchall()
        db.execute('UPDATE assessment_questions SET payload=? WHERE id=?', ('preserved', rows[0][0]))
        db.execute('DELETE FROM assessment_questions WHERE id=?', (rows[1][0],))
    repository.initialize(bank)
    with repository.connection() as db:
        assert db.execute('SELECT COUNT(*) FROM assessment_questions').fetchone()[0] == len(bank.items)
        assert db.execute('SELECT payload FROM assessment_questions WHERE id=?', (rows[0][0],)).fetchone()[0] == 'preserved'
        assert db.execute('SELECT payload FROM assessment_questions WHERE id=?', (rows[1][0],)).fetchone()[0] == rows[1][1]


def test_database_reads_leave_event_loop_available(client, monkeypatch):
    learner = client.post('/api/learners').json()['learner_id']
    service = client.app.state.learners
    original = service.profile
    started, release = threading.Event(), threading.Event()
    workers = []
    def blocked(*args):
        workers.append(threading.get_ident())
        started.set()
        assert release.wait(3)
        return original(*args)
    monkeypatch.setattr(service, 'profile', blocked)
    async def check():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app), base_url='http://local.test') as requests:
            task = asyncio.create_task(requests.get(f'/api/learners/{learner}/profile'))
            # A watchdog prevents a deadlock even if a regression blocks the event loop.
            watchdog = threading.Timer(1.5, release.set)
            watchdog.start()
            try:
                while not started.is_set():
                    await asyncio.sleep(.001)
                assert workers[0] != threading.get_ident()
                assert not release.is_set()
                assert (await requests.get('/health')).status_code == 200
                assert not release.is_set()
            finally:
                release.set()
                watchdog.cancel()
                assert (await task).status_code == 200
    asyncio.run(check())
