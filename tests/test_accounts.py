"""Phase 12B provider contract and isolated account flows; no live emails/users."""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID, uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient
import httpx
import pytest
from pydantic import SecretStr

from app.accounts import AccountService, COOKIE, SupabaseAccounts, digest
from app.auth import AuthenticationError
from app.main import create_app
from app.safeguards import COOKIE as GATE_COOKIE
from tests.test_account_auth import ORIGIN, KEY, claims, token, user_for
from tests.test_staging import CODE, SIGNING, login as gate_login
from tests.test_postgres import pg_settings

FRONTEND = 'https://testserver'
PASSWORD = 'offline-password-only'
HASH = 'a' * 64


class Authority:
    def __init__(self):
        self.payload = claims()
        self.second = claims()
        self.active = self.payload
        self.user = user_for(self.payload) | {'invited_at': '2026-01-01T00:00:00Z'}
        self.used = set()
        self.calls = []
        self.public = False
        self.confirm = False
        self.fail_logout = False
        self.fail_recovery = False
        self.recovery_body = None
        self.refreshes = 0
        self.expires = int(time.time()) + 3600
        self.bad = None

    def bundle(self):
        self.active['exp'] = self.expires
        return {'access_token': token(self.active), 'refresh_token': 'mock-refresh-never-live', 'user': self.user}

    def handle(self, request):
        self.calls.append((request.method, request.url.path, request.url.query))
        assert request.headers['apikey'] == KEY
        assert request.url.host == 'test-project.supabase.co'
        path = request.url.path
        body = json.loads(request.content) if request.content else {}
        if path.endswith('/settings'):
            return httpx.Response(200, json={'disable_signup': not self.public, 'mailer_autoconfirm': self.confirm, 'external': {'email': True, 'anonymous_users': False, 'google': False}})
        if path.endswith('/token'):
            if request.url.query == b'grant_type=password':
                if body.get('password') != PASSWORD:
                    return httpx.Response(400, json={'private': 'invalid credentials'})
            else:
                self.refreshes += 1
                self.expires = int(time.time()) + 3600
            return httpx.Response(200, json=self.bundle())
        if path.endswith('/verify'):
            assert request.method == 'POST' and set(body) == {'type', 'token_hash'}
            if body['token_hash'] != HASH or (body['type'], HASH) in self.used:
                return httpx.Response(403, json={'private': 'invalid link'})
            self.used.add((body['type'], HASH))
            return httpx.Response(200, json=self.bundle())
        if path.endswith('/user'):
            if self.bad == 'signature':
                return httpx.Response(401)
            if request.method == 'PUT':
                assert body == {'password': PASSWORD}
                return httpx.Response(200, json=self.user)
            assert request.headers['authorization'].startswith('Bearer ')
            return httpx.Response(200, json=self.user)
        if path.endswith('/logout'):
            return httpx.Response(500 if self.fail_logout else 204)
        if path.endswith('/recover'):
            self.recovery_body = body
            assert request.url.query == b'redirect_to=https://testserver/auth/recovery'
            return httpx.Response(400 if self.fail_recovery else 200, json={})
        raise AssertionError('Unexpected provider route (especially /signup)')


def enabled(settings, authority):
    settings.account_auth_enabled = True
    settings.supabase_auth_url = ORIGIN
    settings.supabase_auth_publishable_key = SecretStr(KEY)
    settings.frontend_url = FRONTEND
    settings.account_session_encryption_keys = SecretStr(Fernet.generate_key().decode())
    settings.account_invited_ids = SecretStr(authority.payload['sub'] + ',' + authority.second['sub'])
    return settings


@pytest.fixture
def account_client(settings, provider):
    authority = Authority()
    enabled(settings, authority)
    settings.staging_access_enabled = True
    settings.scope_enforcement_enabled = True
    settings.staging_access_code = SecretStr(CODE)
    settings.staging_session_secret = SecretStr(SIGNING)
    adapter = SupabaseAccounts(settings, httpx.MockTransport(authority.handle))
    with TestClient(create_app(settings, provider, account_provider=adapter), base_url=FRONTEND) as client:
        client.authority = authority
        gate_login(client)
        yield client


def bootstrap(client):
    result = client.get('/api/account/bootstrap')
    assert result.status_code == 200, result.text
    return {'Origin': FRONTEND, 'X-CSRF-Token': result.json()['csrf']}


def link(kind='invite', **change):
    params = {'token': HASH, 'type': kind, **change}
    from urllib.parse import urlencode
    return ORIGIN + '/auth/v1/verify?' + urlencode(params)


def activate(client):
    result = client.post('/api/account/accept', json={'email': 'test@example.test', 'link': link()}, headers=bootstrap(client))
    assert result.status_code == 200, result.text
    assert result.json() == {'state': 'activation'}
    assert client.get('/api/account/me').json()['state'] == 'activation'
    result = client.post('/api/account/password', json={'password': PASSWORD}, headers=bootstrap(client))
    assert result.status_code == 200, result.text
    return result


def signin(client):
    result = client.post('/api/account/login', json={'email': 'test@example.test', 'password': PASSWORD}, headers=bootstrap(client))
    assert result.status_code == 200, result.text
    return result


def test_activation_login_logout_no_learner_assignment(account_client, provider):
    client = account_client
    learner = client.post('/api/learners').json()['learner_id']
    before = client.get(f'/api/learners/{learner}/profile').json()
    with client.app.state.repository.connection() as db:
        owners = db.execute('SELECT * FROM staging_resources ORDER BY kind,resource_id').fetchall()
    assert client.get('/api/account/me').status_code == 401
    activate(client)
    response = signin(client)
    raw_cookie = client.cookies.get(COOKIE)
    header = response.headers['set-cookie']
    assert all(item in header for item in ['Secure', 'HttpOnly', 'SameSite=lax', 'Path=/'])
    assert 'Domain=' not in header
    assert client.get('/api/account/me').json()['profile'] == 'linking_pending'
    assert client.get(f'/api/learners/{learner}/profile').json() == before
    with client.app.state.repository.connection() as db:
        assert db.execute('SELECT * FROM staging_resources ORDER BY kind,resource_id').fetchall() == owners
        rows = db.execute('SELECT * FROM account_sessions').fetchall()
        assert len(rows) == 1
        assert rows[0][0] == digest(raw_cookie)
        content = json.dumps(rows)
        assert all(private not in content for private in [raw_cookie, PASSWORD, token(client.authority.payload), 'mock-refresh-never-live'])
        assert db.execute('PRAGMA user_version').fetchone()[0] == 8
    headers = bootstrap(client)
    client.authority.fail_logout = True
    assert client.post('/api/account/logout', json={}, headers=headers).status_code == 200
    client.cookies.set(COOKIE, raw_cookie)
    assert client.get('/api/account/me').status_code == 401
    assert client.get(f'/api/learners/{learner}/profile').json() == before
    assert not provider.calls


@pytest.mark.parametrize('change', ['wrong-password', 'unconfirmed', 'uninvited', 'not-approved', 'signature', 'email-mismatch'])
def test_login_rejections(account_client, change):
    client = account_client
    activate(client)
    email, password = 'test@example.test', PASSWORD
    if change == 'wrong-password': password = 'incorrect'
    if change == 'unconfirmed': client.authority.user['email_confirmed_at'] = None
    if change == 'uninvited': client.authority.user['invited_at'] = None
    if change == 'not-approved': client.app.state.accounts.allowed.clear()
    if change == 'signature': client.authority.bad = 'signature'
    if change == 'email-mismatch': email = 'different@example.test'
    result = client.post('/api/account/login', json={'email': email, 'password': password}, headers=bootstrap(client))
    assert result.status_code == 401
    assert client.get('/api/account/me').status_code == 401
    assert 'private' not in result.text


def test_reused_expired_duplicate_and_invalid_links(account_client):
    client = account_client
    activate(client)
    headers = bootstrap(client)
    assert client.post('/api/account/accept', json={'email': 'test@example.test', 'link': link()}, headers=headers).status_code == 401
    for value in [link(token='b'*64), link(kind='signup'), link()+'&token='+HASH, link().replace(ORIGIN, 'https://attacker.example'), link()+'#access_token=private', link().replace('/verify?', '/verify/extra?')]:
        result = client.post('/api/account/accept', json={'email': 'test@example.test', 'link': value}, headers=headers)
        assert result.status_code == 401


@pytest.mark.parametrize('policy', ['public', 'confirm'])
def test_provider_policy_drift_fails_closed(account_client, policy):
    client = account_client
    headers = bootstrap(client)
    setattr(client.authority, policy, True)
    assert client.get('/api/account/bootstrap').status_code == 503
    assert client.post('/api/account/login', json={'email': 'test@example.test', 'password': PASSWORD}, headers=headers).status_code == 503
    assert not any(path.endswith('/signup') or path.endswith('/token') for _, path, _ in client.authority.calls)


def test_origin_csrf_validation_and_gate(account_client):
    client = account_client
    headers = bootstrap(client)
    body = {'email': 'test@example.test', 'password': PASSWORD}
    for bad_headers in [{}, {'Origin': FRONTEND}, headers | {'Origin': 'https://attacker.example'}, headers | {'Sec-Fetch-Site': 'cross-site'}, headers | {'X-CSRF-Token': 'wrong'}]:
        assert client.post('/api/account/login', json=body, headers=bad_headers).status_code == 403
    before_calls = len(client.authority.calls)
    assert client.post('/api/account/login', json=body | {'email': 'bad'}, headers=headers).status_code == 422
    assert client.post('/api/account/password', json={'password': 'short'}, headers=headers).status_code == 422
    assert client.post('/api/account/login', json=body | {'learner_id': str(uuid4())}, headers=headers).status_code == 422
    assert len(client.authority.calls) == before_calls
    client.cookies.clear()
    assert client.get('/auth/callback').status_code == 200  # Shell only.
    assert client.get('/api/account/bootstrap').status_code == 401
    assert client.post('/api/account/login', json=body, headers=headers).status_code == 401
    assert client.get('/').status_code == 200  # Redirect to the unchanged staging gate.


@pytest.mark.parametrize('expiry', ['idle', 'absolute', 'restricted'])
def test_expiry(account_client, expiry):
    client = account_client
    if expiry != 'restricted': activate(client); signin(client)
    else:
        assert client.post('/api/account/accept', json={'email':'test@example.test','link':link()}, headers=bootstrap(client)).status_code == 200
    nonce = client.cookies.get(COOKIE)
    with client.app.state.repository.connection() as db:
        if expiry == 'idle': db.execute('UPDATE account_sessions SET touched_at=? WHERE nonce_hash=?', (time.time()-86401, digest(nonce)))
        else: db.execute('UPDATE account_sessions SET absolute_expiry=? WHERE nonce_hash=?', (time.time()-1, digest(nonce)))
    assert client.get('/api/account/me').status_code == 401


def test_refresh_rotation_serialized_and_identity_fixed(account_client):
    client = account_client
    activate(client); signin(client)
    nonce = client.cookies.get(COOKIE)
    gate = client.cookies.get(GATE_COOKIE)
    from app.safeguards import read_session
    owner = read_session(gate, client.app.state.settings)
    with client.app.state.repository.connection() as db:
        db.execute('UPDATE account_sessions SET token_expiry=?', (time.time()+1,))
    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: client.app.state.accounts.status(nonce, owner), range(2)))
    assert all(item['state'] == 'ready' for item in results)
    assert client.authority.refreshes == 1
    client.authority.active = client.authority.second
    client.authority.user['id'] = client.authority.second['sub']
    assert client.get('/api/account/me').status_code == 401


def test_password_recovery_generic_and_revokes_all_sessions(account_client):
    client = account_client
    activate(client); signin(client)
    old = client.cookies.get(COOKIE)
    result = client.post('/api/account/recover', json={'email':'test@example.test'}, headers=bootstrap(client))
    assert result.status_code == 202
    client.authority.fail_recovery = True
    unknown = client.post('/api/account/recover', json={'email':'unknown@example.test'}, headers=bootstrap(client))
    assert unknown.status_code == result.status_code and unknown.json() == result.json()
    result = client.post('/api/account/accept', json={'email':'test@example.test','link':link('recovery', redirect_to='https://attacker.example')}, headers=bootstrap(client) | {'X-Account-Flow':'recovery'})
    assert result.status_code == 200
    assert client.get('/api/account/me').json()['state'] == 'recovery'
    assert client.post('/api/account/password', json={'password':PASSWORD}, headers=bootstrap(client)).status_code == 200
    client.cookies.set(COOKIE, old)
    assert client.get('/api/account/me').status_code == 401
    assert any(query == b'scope=global' for _, _, query in client.authority.calls)


def test_sessions_isolated_by_nonce_and_staging_owner(account_client):
    client = account_client
    activate(client); signin(client)
    original = client.cookies.get(COOKIE)
    gate = client.cookies.get(GATE_COOKIE)
    client.cookies.delete(GATE_COOKIE)
    gate_login(client)
    assert client.get('/api/account/me').status_code == 401
    client.cookies.clear(); client.cookies.set(GATE_COOKIE, gate); client.cookies.set(COOKIE, original)
    assert client.get('/api/account/me').status_code == 200
    client.cookies.set(COOKIE, original + 'x')
    assert client.get('/api/account/me').status_code == 401


def test_password_endpoint_cannot_be_used_by_ready_session(account_client):
    client = account_client
    activate(client); signin(client)
    assert client.post('/api/account/password', json={'password':PASSWORD}, headers=bootstrap(client)).status_code == 401


def test_disabled_adds_no_schema_or_entrypoint(client):
    assert client.get('/auth/sign-in').status_code == 404
    assert client.get('/api/account/bootstrap').status_code == 404
    assert 'Open account sign-in' not in client.get('/').text
    with client.app.state.repository.connection() as db:
        assert not db.execute("SELECT 1 FROM sqlite_master WHERE name='account_sessions'").fetchone()


def test_rate_limit(account_client):
    client = account_client
    headers = bootstrap(client)
    for _ in range(10):
        assert client.post('/api/account/login', json={'email':'test@example.test','password':'incorrect'}, headers=headers).status_code == 401
    assert client.post('/api/account/login', json={'email':'test@example.test','password':'incorrect'}, headers=headers).status_code == 429


def test_additive_repeat_and_rollback(account_client):
    service = account_client.app.state.accounts
    learner = account_client.post('/api/learners').json()['learner_id']
    before = account_client.get(f'/api/learners/{learner}/profile').json()
    service.initialize(); service.initialize()
    assert account_client.get(f'/api/learners/{learner}/profile').json() == before
    with pytest.raises(RuntimeError):
        with service.transaction() as db:
            db.execute('INSERT INTO account_beta_members VALUES (?,?)', (str(uuid4()), time.time()))
            raise RuntimeError('simulated failure')
    with service.transaction() as db:
        assert db.execute('SELECT count(*) FROM account_beta_members').fetchone()[0] == 0


def test_no_secret_in_errors_or_logs(account_client, caplog):
    result = account_client.post('/api/account/accept', json={'email':'test@example.test','link':link(token='b'*64)}, headers=bootstrap(account_client))
    assert result.status_code == 401
    assert all(secret not in result.text + caplog.text for secret in [HASH, PASSWORD, KEY, 'private', 'mock-refresh-never-live'])


def test_encryption_key_rotation(account_client):
    client = account_client
    activate(client); signin(client)
    settings = client.app.state.settings
    settings.account_session_encryption_keys = SecretStr(Fernet.generate_key().decode() + ',' + settings.account_session_encryption_keys.get_secret_value())
    client.app.state.accounts = AccountService(client.app.state.repository, settings, client.app.state.accounts.provider)
    assert client.get('/api/account/me').status_code == 200


def test_provider_session_read_contract(settings):
    from app.auth import VerifiedAccount
    adapter = SupabaseAccounts(enabled(settings, Authority()))
    account = VerifiedAccount(UUID(str(uuid4())), UUID(str(uuid4())), int(time.time())+60)
    class DB:
        calls = []
        def execute(self, query, args=()):
            self.calls.append((query, args)); return self
        def fetchone(self): return None
    db = DB()
    adapter.storage_ready(db)
    assert adapter.session_exists(db, account) is False
    assert db.calls == [('SELECT id,user_id FROM auth.sessions LIMIT 0', ()),
        ('SELECT 1 FROM auth.sessions WHERE id=? AND user_id=?', (str(account.provider_session_id), str(account.account_id)))]


@pytest.mark.parametrize('status,body', [(302, '{}'), (500, 'PRIVATE'), (200, 'not-json'), (200, '[]'), (200, 'x'*65537)],
    ids=['redirect', 'upstream-error', 'invalid-json', 'array', 'oversized'])
def test_account_provider_response_boundary(settings, status, body, caplog):
    adapter = SupabaseAccounts(enabled(settings, Authority()), httpx.MockTransport(
        lambda request: httpx.Response(status, text=body, headers={'Location':'https://attacker.example'})))
    with pytest.raises(AuthenticationError) as caught:
        adapter.policy()
    assert caught.value.status == 503
    assert KEY not in str(caught.value) + caplog.text and 'PRIVATE' not in str(caught.value) + caplog.text


def test_account_provider_total_deadline(settings):
    import asyncio
    async def slow(request):
        await asyncio.sleep(1)
        raise AssertionError('Total deadline must cancel this provider request')
    adapter = SupabaseAccounts(enabled(settings, Authority()), httpx.MockTransport(slow))
    adapter.timeout = .01
    with pytest.raises(AuthenticationError) as caught:
        adapter.policy()
    assert caught.value.status == 503


def test_postgres_account_migration_refresh_revocation_and_rollback(pg_settings, provider):
    authority = Authority()
    enabled(pg_settings, authority)
    pg_settings.staging_access_enabled = True
    pg_settings.scope_enforcement_enabled = True
    pg_settings.staging_access_code = SecretStr(CODE)
    pg_settings.staging_session_secret = SecretStr(SIGNING)
    class LocalProvider(SupabaseAccounts):
        # Generic disposable PostgreSQL has no managed Supabase auth schema.
        # Mock only provider-session existence; exercise real app schema/locks.
        revoked = False
        def storage_ready(self, db): pass
        def session_exists(self, db, candidate): return not self.revoked
    adapter = LocalProvider(pg_settings, httpx.MockTransport(authority.handle))
    with TestClient(create_app(pg_settings, provider, account_provider=adapter), base_url=FRONTEND) as client:
        client.authority = authority
        gate_login(client)
        test_additive_repeat_and_rollback(client)
        activate(client); signin(client)
        nonce = client.cookies.get(COOKIE)
        from app.safeguards import read_session
        owner = read_session(client.cookies.get(GATE_COOKIE), pg_settings)
        with client.app.state.accounts.transaction() as db:
            db.execute('UPDATE account_sessions SET token_expiry=?', (time.time()+1,))
        with ThreadPoolExecutor(max_workers=2) as pool:
            assert all(item['state'] == 'ready' for item in pool.map(lambda _: client.app.state.accounts.status(nonce, owner), range(2)))
        assert authority.refreshes == 1
        adapter.revoked = True
        assert client.get('/api/account/me').status_code == 401
        with client.app.state.accounts.transaction() as db:
            assert db.execute('PRAGMA user_version').fetchone()[0] == 8
    # Feature rollback leaves additive rows in place, with legacy access intact.
    pg_settings.account_auth_enabled = False
    with TestClient(create_app(pg_settings, provider), base_url=FRONTEND) as rolled_back:
        assert rolled_back.get('/health').status_code == 200
        gate_login(rolled_back)
        assert rolled_back.get('/api/account/bootstrap').status_code == 404
