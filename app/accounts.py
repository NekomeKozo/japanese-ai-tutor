"""Phase 12B account boundary. No learner IDs, claims or learning-data access.

All provider requests execute in a worker, never the ASGI event loop. A database
transaction serializes refresh rotation across workers (PostgreSQL row locks /
SQLite BEGIN IMMEDIATE). Tokens are encrypted at rest; cookie
nonces are hashed. Passwords and email-link secrets are never persisted.
"""
from contextlib import contextmanager
from datetime import datetime, timezone
import asyncio
import hashlib
import hmac
import json
import re
import secrets
import time
from urllib.parse import parse_qs, urlsplit

from cryptography.fernet import Fernet, InvalidToken, MultiFernet
import httpx

from app.auth import AuthenticationError, _narrow_claims, _unique_object
from app.errors import TutorError
from app.storage import postgres_connection
import psycopg
import logging

COOKIE = '__Host-goigrow_session'
ABSOLUTE = 7 * 86400
IDLE = 86400
RESTRICTED = 600


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()


def link_hash(value, kind, origin):
    """Parse only the provider's original email link; never navigate to it.

    Default templates use GET token= (already a token HASH). POST /verify takes
    token_hash= instead and returns credentials to this server, without redirects.
    Reject tracking wrappers, duplicate parameters and alternate verification types.
    """
    try:
        if len(value) > 4096 or any(ord(c) <= 32 for c in value):
            raise ValueError()
        url = urlsplit(value)
        expected = urlsplit(origin)
        if (url.scheme != expected.scheme or url.netloc != expected.netloc
                or url.path != '/auth/v1/verify' or url.fragment or url.username or url.password):
            raise ValueError()
        query = parse_qs(url.query, strict_parsing=True, keep_blank_values=True)
        if (not set(query) <= {'token', 'type', 'redirect_to'} or any(len(v) != 1 for v in query.values())
                or query.get('type') != [kind]):
            raise ValueError()
        token = query['token'][0]
        if not re.fullmatch(r'[A-Za-z0-9_-]{20,256}', token):
            raise ValueError()
        # redirect_to is NEVER followed, returned to the browser, or sent upstream.
        return token
    except (ValueError, KeyError, TypeError):
        raise AuthenticationError() from None


class SupabaseAccounts:
    """Publishable-key adapter; no signup endpoint or administrative credential."""
    def __init__(self, settings, transport=None):
        self.origin = settings.supabase_auth_url
        self.key = settings.supabase_auth_publishable_key.get_secret_value()
        self.timeout = settings.supabase_auth_timeout_seconds
        self.transport = transport

    def request(self, method, path, *, body=None, token=None, empty=False):
        # Called only in a worker. Total deadline includes connect + all chunks,
        # rather than allowing a slow response to reset a per-read timeout.
        return asyncio.run(self._request(method, path, body=body, token=token, empty=empty))

    async def _request(self, method, path, *, body=None, token=None, empty=False):
        headers = {'apikey': self.key}
        if token:
            headers['Authorization'] = 'Bearer ' + token
        try:
            async with asyncio.timeout(self.timeout), httpx.AsyncClient(timeout=self.timeout, follow_redirects=False, transport=self.transport) as client:
                async with client.stream(method, self.origin + '/auth/v1' + path, json=body, headers=headers) as response:
                    if response.status_code in (400, 401, 403, 422):
                        raise AuthenticationError()
                    if not 200 <= response.status_code < 300:
                        raise AuthenticationError(unavailable=True)
                    data = bytearray()
                    async for chunk in response.aiter_bytes():
                        data.extend(chunk)
                        if len(data) > 65536:
                            raise AuthenticationError(unavailable=True)
                    if empty:
                        return None
                    result = json.loads(data, object_pairs_hook=_unique_object)
                    if not isinstance(result, dict):
                        raise ValueError()
                    return result
        except AuthenticationError:
            raise
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, RecursionError):
            raise AuthenticationError(unavailable=True) from None

    def policy(self):
        config = self.request('GET', '/settings')
        external = config.get('external', {})
        if (config.get('disable_signup') is not True or config.get('mailer_autoconfirm') is not False
                or not isinstance(external, dict) or external.get('email') is not True
                or any(value is not False for name, value in external.items() if name != 'email')):
            raise AuthenticationError(unavailable=True)

    def login(self, email, password):
        return self.request('POST', '/token?grant_type=password', body={'email': email, 'password': password})

    def verify_link(self, value, kind):
        return self.request('POST', '/verify', body={'token_hash': link_hash(value, kind, self.origin), 'type': kind})

    def refresh(self, token):
        return self.request('POST', '/token?grant_type=refresh_token', body={'refresh_token': token})

    def user(self, token):
        candidate = _narrow_claims(token, self.origin + '/auth/v1')
        user = self.request('GET', '/user', token=token)
        try:
            confirmed = datetime.fromisoformat(user['email_confirmed_at'].replace('Z', '+00:00'))
            now = datetime.now(timezone.utc)
            if (user.get('id') != str(candidate.account_id) or user.get('is_anonymous') is not False
                    or not isinstance(user.get('email'), str) or not user['email']
                    or confirmed.tzinfo is None or confirmed > now
                    or candidate.expires_at <= time.time()):
                raise ValueError()
        except (ValueError, TypeError, KeyError, AttributeError):
            raise AuthenticationError() from None
        return candidate, user

    def password(self, token, password):
        self.request('PUT', '/user', token=token, body={'password': password})

    def recover(self, email, frontend):
        self.request('POST', '/recover?redirect_to=' + frontend + '/auth/recovery', body={'email': email}, empty=True)

    def logout(self, token, scope='local'):
        self.request('POST', '/logout?scope=' + scope, token=token, empty=True)

    def storage_ready(self, db):
        db.execute('SELECT id,user_id FROM auth.sessions LIMIT 0')

    def session_exists(self, db, candidate):
        return bool(db.execute('SELECT 1 FROM auth.sessions WHERE id=? AND user_id=?',
            (str(candidate.provider_session_id), str(candidate.account_id))).fetchone())


class AccountService:
    def __init__(self, repository, settings, provider=None, clock=time.time):
        self.repository = repository
        self.settings = settings
        self.provider = provider or SupabaseAccounts(settings)
        self.clock = clock
        keys = settings.account_session_encryption_keys.get_secret_value().split(',')
        self.cipher = MultiFernet([Fernet(key.encode()) for key in keys])
        self.csrf_key = hashlib.sha256(('csrf:' + keys[0]).encode()).digest()
        self.key_version = hashlib.sha256(keys[0].encode()).hexdigest()[:16]
        self.allowed = set(settings.account_invited_ids.get_secret_value().split(','))
        self.bootstrap_owners = set(filter(None, settings.account_owner_bootstrap_ids.get_secret_value().split(',')))

    def initialize(self):
        # Only called with the feature enabled. Separate additive schema marker;
        # legacy learner migrations/version 8 are deliberately untouched.
        with self.repository.connection() as db:
            db.execute('BEGIN IMMEDIATE')
            db.execute('''CREATE TABLE IF NOT EXISTS account_sessions (
                nonce_hash TEXT PRIMARY KEY, staging_owner TEXT NOT NULL,
                account_id TEXT, provider_session TEXT, purpose TEXT NOT NULL,
                encrypted_tokens TEXT, created_at REAL NOT NULL, touched_at REAL NOT NULL,
                absolute_expiry REAL NOT NULL, token_expiry REAL)''')
            db.execute('''CREATE TABLE IF NOT EXISTS account_beta_members (
                account_id TEXT PRIMARY KEY, activated_at REAL NOT NULL)''')
            db.execute('CREATE INDEX IF NOT EXISTS account_sessions_account ON account_sessions(account_id)')
            if self.repository.database_url:
                # Read-only capability check, never grant permissions or recreate
                # provider-managed tables. Missing privileges block activation.
                self.provider.storage_ready(db)

    @contextmanager
    def transaction(self):
        if self.repository.database_url:
            try:
                # Account row locks serialize refresh without holding the legacy
                # application's advisory lock during remote Auth requests.
                with postgres_connection(self.repository.database_url, serialize=False) as db:
                    yield db
            except psycopg.Error as exc:
                logging.getLogger(__name__).error('Account storage failure: %s', type(exc).__name__)
                raise AuthenticationError(unavailable=True) from None
        else:
            with self.repository.connection() as db:
                db.execute('BEGIN IMMEDIATE')
                yield db

    def encrypt(self, bundle):
        return 'v1:' + self.key_version + ':' + self.cipher.encrypt(json.dumps(bundle).encode()).decode()

    def decrypt(self, encrypted):
        try:
            version, key_id, ciphertext = encrypted.split(':', 2)
            if version != 'v1' or not re.fullmatch(r'[a-f0-9]{16}', key_id):
                raise ValueError()
            return json.loads(self.cipher.decrypt(ciphertext.encode()))
        except (InvalidToken, ValueError, TypeError, AttributeError):
            raise AuthenticationError() from None

    def csrf(self, nonce):
        return hmac.new(self.csrf_key, nonce.encode(), hashlib.sha256).hexdigest()

    def row(self, db, nonce, owner):
        if not nonce or not re.fullmatch(r'[A-Za-z0-9_-]{43}', nonce):
            return None
        lock = ' FOR UPDATE' if self.repository.database_url else ''
        row = db.execute('SELECT * FROM account_sessions WHERE nonce_hash=? AND staging_owner=?' + lock, (digest(nonce), owner)).fetchone()
        if row and (row[8] <= self.clock() or row[7] + IDLE <= self.clock()):
            db.execute('DELETE FROM account_sessions WHERE nonce_hash=?', (digest(nonce),))
            return None
        return row

    def bootstrap(self, nonce, owner):
        self.provider.policy()
        with self.transaction() as db:
            if not self.row(db, nonce, owner):
                nonce = self.insert(db, owner, 'preauth')
        return nonce, self.csrf(nonce)

    def insert(self, db, owner, purpose, bundle=None, candidate=None):
        nonce = secrets.token_urlsafe(32)
        now = self.clock()
        expiry = now + (ABSOLUTE if purpose == 'ready' else RESTRICTED)
        encrypted = self.encrypt(bundle) if bundle else None
        db.execute('INSERT INTO account_sessions VALUES (?,?,?,?,?,?,?,?,?,?)',
            (digest(nonce), owner, str(candidate.account_id) if candidate else None,
             str(candidate.provider_session_id) if candidate else None, purpose, encrypted,
             now, now, expiry, candidate.expires_at if candidate else None))
        # Bounded cleanup of expired server records, including unauthenticated ones.
        db.execute('DELETE FROM account_sessions WHERE absolute_expiry<=? OR touched_at<=?', (now, now-IDLE))
        return nonce

    def check_csrf(self, nonce, supplied, owner):
        with self.transaction() as db:
            row = self.row(db, nonce, owner)
        if not row or not isinstance(supplied, str) or not hmac.compare_digest(self.csrf(nonce), supplied):
            raise TutorError('account_csrf', 'Refresh the account page and try again.', 403)

    def verified(self, bundle, db, *, expected=None, email=None, purpose='ready'):
        if (not isinstance(bundle, dict) or not isinstance(bundle.get('access_token'), str)
                or not isinstance(bundle.get('refresh_token'), str)
                or not 1 <= len(bundle['refresh_token']) <= 4096):
            raise AuthenticationError()
        candidate, user = self.provider.user(bundle['access_token'])
        account = str(candidate.account_id)
        if account not in self.allowed or (expected and account != expected) or (email and user['email'].casefold() != email.casefold()):
            raise AuthenticationError()
        # Only an explicitly designated owner may use password login/recovery
        # without an invitation. The invitation endpoint always requires one.
        if account not in self.bootstrap_owners or purpose == 'activation':
            try:
                invited = datetime.fromisoformat(user['invited_at'].replace('Z', '+00:00'))
                if invited.tzinfo is None or invited > datetime.now(timezone.utc):
                    raise ValueError()
            except (ValueError, TypeError, KeyError, AttributeError):
                raise AuthenticationError() from None
        if self.repository.database_url and not self.provider.session_exists(db, candidate):
            raise AuthenticationError()
        return candidate

    def require_ready_membership(self, db, candidate):
        account = str(candidate.account_id)
        if account not in self.bootstrap_owners and not db.execute(
                'SELECT 1 FROM account_beta_members WHERE account_id=?', (account,)).fetchone():
            raise AuthenticationError()

    def authenticate(self, nonce, owner, email, secret, purpose):
        self.provider.policy()
        bundle = (self.provider.login(email, secret) if purpose == 'ready'
                  else self.provider.verify_link(secret, 'invite' if purpose == 'activation' else 'recovery'))
        # Never save user/provider metadata alongside the required credentials.
        bundle = {key: bundle.get(key) for key in ('access_token', 'refresh_token')}
        try:
            with self.transaction() as db:
                if not self.row(db, nonce, owner):
                    raise AuthenticationError()
                candidate = self.verified(bundle, db, email=email, purpose=purpose)
                if purpose == 'ready':
                    self.require_ready_membership(db, candidate)
                fresh = self.insert(db, owner, purpose, bundle, candidate)
                db.execute('DELETE FROM account_sessions WHERE nonce_hash=?', (digest(nonce),))
            return fresh
        except TutorError:
            if isinstance(bundle.get('access_token'), str):
                try:
                    self.provider.logout(bundle['access_token'])
                except AuthenticationError:
                    pass
            raise

    def resolve(self, db, nonce, owner):
        row = self.row(db, nonce, owner)
        if not row or row[4] == 'preauth':
            raise AuthenticationError()
        bundle = self.decrypt(row[5])
        if row[9] <= self.clock() + 30:
            bundle = self.provider.refresh(bundle['refresh_token'])
            bundle = {key: bundle.get(key) for key in ('access_token', 'refresh_token')}
        candidate = self.verified(bundle, db, expected=row[2], purpose=row[4])
        if row[4] == 'ready':
            self.require_ready_membership(db, candidate)
        if str(candidate.provider_session_id) != row[3]:
            raise AuthenticationError()
        db.execute('UPDATE account_sessions SET encrypted_tokens=?,token_expiry=?,touched_at=? WHERE nonce_hash=?',
            (self.encrypt(bundle), candidate.expires_at, self.clock(), digest(nonce)))
        return row, bundle

    def status(self, nonce, owner):
        self.provider.policy()
        with self.transaction() as db:
            row, _ = self.resolve(db, nonce, owner)
            linked = (self.repository.account_links_ready and row[4] == 'ready' and db.execute(
                'SELECT 1 FROM account_learner_links WHERE account_id=?', (row[2],)).fetchone())
            return {'state': row[4], 'profile': 'linked' if linked else 'linking_pending', 'expires_at': row[8]}

    def principal(self, nonce, owner):
        from app.learner_access import Principal
        self.provider.policy()
        with self.transaction() as db:
            row, _ = self.resolve(db, nonce, owner)
            if row[4] != 'ready':
                raise AuthenticationError()
            return Principal(str(row[2]), row[0], row[3], row[6])

    def set_password(self, nonce, owner, password):
        self.provider.policy()
        with self.transaction() as db:
            row, bundle = self.resolve(db, nonce, owner)
            if row[4] not in ('activation', 'recovery'):
                raise AuthenticationError()
            self.provider.password(bundle['access_token'], password)
            db.execute('INSERT OR IGNORE INTO account_beta_members VALUES (?,?)', (row[2], self.clock()))
            # A password reset revokes every local application session; never
            # trust residual provider JWTs as proof of active session membership.
            db.execute('DELETE FROM account_sessions WHERE account_id=?', (row[2],))
        try:
            self.provider.logout(bundle['access_token'], scope='global')
        except AuthenticationError:
            pass  # App revocation has already committed; sign in afresh.

    def logout(self, nonce, owner):
        token = None
        with self.transaction() as db:
            row = self.row(db, nonce, owner)
            if row:
                try:
                    token = self.decrypt(row[5])['access_token'] if row[5] else None
                except (AuthenticationError, KeyError):
                    pass
                db.execute('DELETE FROM account_sessions WHERE nonce_hash=?', (digest(nonce),))
        if token:
            try:
                self.provider.logout(token)
            except AuthenticationError:
                pass  # Local logout must succeed even during provider outage.

    def recover(self, email):
        self.provider.policy()
        try:
            self.provider.recover(email, self.settings.frontend_url.rstrip('/'))
        except AuthenticationError:
            pass  # Same generic result for unknown users, quotas and delivery errors.
