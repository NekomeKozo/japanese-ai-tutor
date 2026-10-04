from uuid import uuid4
import pytest
from app.safeguards import COOKIE
from tests.test_staging import gated, login


def headers(response):
    assert response.headers['cache-control'] == 'no-store'
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['x-frame-options'] == 'DENY'
    assert "form-action 'self'" in response.headers['content-security-policy']
    assert "object-src 'none'" in response.headers['content-security-policy']
    assert 'microphone=(self)' in response.headers['permissions-policy']


def test_all_rejection_paths_keep_security_headers(gated, settings):
    settings.environment = 'staging'
    for path in ['/docs', '/docs-malicious', '/redoc-copy', '/api/learners', '/reference/book.pdf', '/.env']:
        response = gated.get(path)
        assert response.status_code == 401
        headers(response)
        assert response.headers['strict-transport-security'] == 'max-age=15552000'
    gated.app.state.speech_uploads = 2
    response = gated.post(f'/api/learners/{uuid4()}/speech/transcribe', content=b'not audio')
    assert response.status_code == 429
    headers(response)
    assert gated.app.state.speech_uploads == 2


def test_unexpected_error_is_generic_and_uncacheable(gated):
    @gated.app.get('/test-hardening-error')
    def error():
        raise RuntimeError('synthetic confidential diagnostic')
    login(gated)
    result = gated.get('/test-hardening-error')
    assert result.status_code == 500
    assert 'confidential' not in result.text
    headers(result)


def test_cross_learner_reads_and_mutations_remain_denied(gated, provider):
    login(gated)
    owner = gated.post('/api/learners').json()['learner_id']
    session = gated.post(f'/api/learners/{owner}/sessions').json()['session_id']
    gated.cookies.clear()
    login(gated)
    other = gated.post('/api/learners').json()['learner_id']
    for suffix in ['jlpt/history','conversations/active','reviews/history','audio/progress']:
        assert gated.get(f'/api/learners/{owner}/{suffix}').status_code == 404
    mutations = [('/preferences','PATCH',{'primary_goal':'travel'}),('/conversations','POST',{'scenario_id':'introductions'}),('/jlpt/sessions','POST',{}),(f'/sessions/{session}/close','POST',{}),(f'/reviews/{uuid4()}/recall','POST',{})]
    for suffix, method, body in mutations:
        result = gated.request(method,f'/api/learners/{owner}{suffix}',json=body)
        assert result.status_code == 404
        headers(result)
    # Owning another learner does not make the first learner's session valid.
    assert gated.get(f'/api/learners/{other}/sessions/{session}').status_code == 404
    assert not provider.calls


def test_origin_and_private_file_protection(gated):
    login(gated)
    for origin in ['null','https://attacker.example','http://testserver.attacker.example']:
        assert gated.post('/api/learners',headers={'Origin':origin}).status_code == 403
    for path in ['/static/../.env','/static/%2e%2e/.env','/static/%2e%2e/reference/book.pdf','/data/test.sqlite3','/knowledge_base/private.json','/references/book.pdf']:
        response = gated.get(path)
        assert response.status_code in (404,401)
        assert response.headers['cache-control'] == 'no-store'
    response = gated.options('/api/learners',headers={'Origin':'https://attacker.example','Access-Control-Request-Method':'POST'})
    assert 'access-control-allow-origin' not in response.headers

def test_separate_browser_restoration_never_transfers_or_overwrites(gated):
    original_token = login(gated)
    original = gated.post('/api/learners').json()['learner_id']
    before = gated.get(f'/api/learners/{original}/profile').json()
    gated.cookies.clear()
    login(gated)
    assert gated.get(f'/api/learners/{original}/profile').status_code == 404
    separate = gated.post('/api/learners').json()['learner_id']
    assert separate != original
    gated.cookies.clear()
    gated.cookies.set(COOKIE, original_token)
    assert gated.get(f'/api/learners/{original}/profile').json() == before
    assert gated.get(f'/api/learners/{separate}/profile').status_code == 404
