"""Phase 12A verification utility; no cookies, storage writes or ownership grants.

Supabase /auth/v1/user is the signature-verification authority over trusted TLS.
Locally decoded claims only narrow acceptance; decoding NEVER authenticates a user.
Phase 12B uses the same narrow claims and trusted provider authority in its BFF.
"""
import asyncio
import base64
from dataclasses import dataclass
from datetime import datetime, timezone
import json
import re
import time
from uuid import UUID

import httpx

from app.config import Settings
from app.errors import TutorError


class AuthenticationError(TutorError):
    def __init__(self, *, unavailable=False):
        super().__init__('account_auth_unavailable' if unavailable else 'account_auth_required',
                         'Account sign-in is unavailable. Please try again later.' if unavailable
                         else 'Please sign in to continue.', 503 if unavailable else 401)


@dataclass(frozen=True)
class VerifiedAccount:
    account_id: UUID
    provider_session_id: UUID
    expires_at: int


def _unique_object(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError('Duplicate claim')
        result[key] = value
    return result


def _decode_part(value):
    decoded = base64.b64decode(value + '=' * (-len(value) % 4), altchars=b'-_', validate=True)
    result = json.loads(decoded, object_pairs_hook=_unique_object)
    if not isinstance(result, dict):
        raise ValueError('Invalid token object')
    return result


def _narrow_claims(token, issuer):
    """Reject ineligible claims early, without granting identity or following URLs."""
    try:
        if (not isinstance(token, str) or len(token) > 16384
                or not re.fullmatch(r'[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+', token)):
            raise ValueError('Invalid token')
        header, payload, _ = token.split('.')
        header, claims = _decode_part(header), _decode_part(payload)
        if header.get('alg') not in ('RS256', 'ES256', 'HS256') or header.get('typ') != 'JWT':
            raise ValueError('Unsupported token')
        now = time.time()
        if (claims.get('iss') != issuer or claims.get('aud') != 'authenticated'
                or claims.get('role') != 'authenticated' or claims.get('is_anonymous') is not False):
            raise ValueError('Ineligible token')
        # No grace for expiry. iat is required; nbf is optional but enforced.
        for name in ('exp', 'iat'):
            if type(claims.get(name)) is not int:
                raise ValueError('Invalid time claim')
        if claims['exp'] <= now or claims['iat'] > now or claims['iat'] >= claims['exp']:
            raise ValueError('Expired token')
        if 'nbf' in claims and (type(claims['nbf']) is not int or claims['nbf'] > now):
            raise ValueError('Token not active')
        account = VerifiedAccount(UUID(claims['sub']), UUID(claims['session_id']), claims['exp'])
        if str(account.account_id) != claims['sub'] or str(account.provider_session_id) != claims['session_id']:
            raise ValueError('Noncanonical identifier')
        return account
    except (ValueError, TypeError, KeyError, AttributeError, RecursionError):
        raise AuthenticationError() from None


class SupabaseAccountVerifier:
    """Stateless online verification. Caller owns a dedicated AsyncClient lifecycle.

    Uses a publishable key, not service-role/admin credentials. A verified account
    is not permission to retrieve a learner, nor proof of a live beta invitation.
    Provider/global logout revocation still needs the Phase 12B session design.
    """
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        # Revalidate even if a caller modified Settings after construction.
        config = Settings.model_validate(settings.model_dump())
        if not config.supabase_auth_url:
            raise AuthenticationError(unavailable=True)
        self._issuer = config.supabase_auth_url + '/auth/v1'
        self._key = config.supabase_auth_publishable_key.get_secret_value()
        self._timeout = config.supabase_auth_timeout_seconds
        self._client = client

    async def verify(self, token: str) -> VerifiedAccount:
        candidate = _narrow_claims(token, self._issuer)
        try:
            async with asyncio.timeout(self._timeout):
                async with self._client.stream('GET', self._issuer + '/user',
                        headers={'apikey': self._key, 'Authorization': 'Bearer ' + token},
                        timeout=self._timeout, follow_redirects=False) as response:
                    if response.status_code in (401, 403):
                        raise AuthenticationError()
                    if response.status_code != 200:
                        raise AuthenticationError(unavailable=True)
                    body = bytearray()
                    async for chunk in response.aiter_bytes():
                        body.extend(chunk)
                        if len(body) > 65536:
                            raise AuthenticationError(unavailable=True)
            user = json.loads(body, object_pairs_hook=_unique_object)
            if not isinstance(user, dict):
                raise ValueError('Invalid provider response')
            # This check only happens AFTER the provider verifies the signature.
            if (user.get('id') != str(candidate.account_id) or user.get('is_anonymous') is not False
                    or not user.get('email') or not user.get('email_confirmed_at')):
                raise AuthenticationError()
            confirmed = datetime.fromisoformat(user['email_confirmed_at'].replace('Z', '+00:00'))
            if confirmed.tzinfo is None or confirmed > datetime.now(timezone.utc):
                raise AuthenticationError()
            if candidate.expires_at <= time.time():
                raise AuthenticationError()
            return candidate
        except AuthenticationError:
            raise
        except (httpx.HTTPError, TimeoutError, ValueError, TypeError, AttributeError, RecursionError):
            # No upstream response body, token, key or personal data in errors/logs.
            raise AuthenticationError(unavailable=True) from None
