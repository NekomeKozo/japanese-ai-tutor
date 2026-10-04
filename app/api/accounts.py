"""BFF account routes. Every mutation needs staging access, Origin and CSRF."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from starlette.concurrency import run_in_threadpool
import re
import hashlib
import hmac
import logging

from app.accounts import ABSOLUTE, COOKIE
from app.errors import TutorError

router = APIRouter()
logger = logging.getLogger(__name__)
PAGES = ('/auth/sign-in', '/auth/callback', '/auth/recovery')


class Email(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    email: str = Field(min_length=3, max_length=254)

    @field_validator('email')
    @classmethod
    def email_valid(cls, value):
        if not re.fullmatch(r'[^@\s<>]+@[^@\s<>]+\.[^@\s<>]+', value):
            raise ValueError('Enter a valid email address')
        return value


class Credentials(Email):
    password: SecretStr = Field(min_length=1, max_length=128)


class Verification(Email):
    link: SecretStr = Field(min_length=20, max_length=4096)


class Password(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)
    password: SecretStr = Field(min_length=12, max_length=128)


def service(request):
    if not request.app.state.settings.account_auth_enabled:
        raise TutorError('not_found', 'Account sign-in is not enabled yet.', 404)
    return request.app.state.accounts


def owner(request):
    return getattr(request.state, 'staging_identity', None) or 'development'


def nonce(request):
    return request.cookies.get(COOKIE)


def cookie(response, value):
    response.set_cookie(COOKIE, value, max_age=ABSOLUTE, secure=True, httponly=True,
                        samesite='lax', path='/')


async def mutation(request, *, recovery=False, email=None):
    accounts = service(request)
    settings = request.app.state.settings
    origin = request.headers.get('origin')
    if (origin != settings.frontend_url.rstrip('/')
            or request.headers.get('sec-fetch-site') == 'cross-site'):
        raise TutorError('account_origin', 'Open GoiGrow to continue.', 403)
    # Keep attempts across accounts and gate-cookie rotations bounded. Shared
    # persistent provider limits supplement these small single-worker app limits.
    identity = request.client.host if request.client else 'unknown'
    request.app.state.account_limiter.take(identity, 10, 600)
    request.app.state.account_limiter.take('global', 60, 600)
    if email:
        email_hash = hmac.new(accounts.csrf_key, email.casefold().encode(), hashlib.sha256).hexdigest()
        request.app.state.account_limiter.take('email:' + email_hash, 10, 600)
    if recovery:
        request.app.state.account_limiter.take('email-global', 2, 3600)
    await run_in_threadpool(accounts.check_csrf, nonce(request), request.headers.get('x-csrf-token'), owner(request))
    return accounts


@router.get('/auth/sign-in', include_in_schema=False)
@router.get('/auth/callback', include_in_schema=False)
@router.get('/auth/recovery', include_in_schema=False)
async def page(request: Request):
    service(request)
    return HTMLResponse(request.app.state.account_html)


@router.get('/api/account/bootstrap')
async def bootstrap(request: Request):
    service(request)
    identity = request.client.host if request.client else 'unknown'
    request.app.state.account_limiter.take('bootstrap:' + identity, 30, 60)
    request.app.state.account_limiter.take('bootstrap-global', 120, 60)
    value, csrf = await run_in_threadpool(service(request).bootstrap, nonce(request), owner(request))
    response = JSONResponse({'csrf': csrf})
    cookie(response, value)
    return response


@router.get('/api/account/me')
async def me(request: Request):
    return await run_in_threadpool(service(request).status, nonce(request), owner(request))


@router.post('/api/account/login')
async def login(request: Request, body: Credentials):
    accounts = await mutation(request, email=body.email)
    value = await run_in_threadpool(accounts.authenticate, nonce(request), owner(request),
                                   body.email, body.password.get_secret_value(), 'ready')
    response = JSONResponse({'state': 'ready', 'profile': 'linking_pending'})
    cookie(response, value)
    logger.info('Account security event=login outcome=success')
    return response


@router.post('/api/account/accept')
async def accept(request: Request, body: Verification):
    accounts = await mutation(request, email=body.email)
    purpose = 'recovery' if request.headers.get('x-account-flow') == 'recovery' else 'activation'
    value = await run_in_threadpool(accounts.authenticate, nonce(request), owner(request),
                                   body.email, body.link.get_secret_value(), purpose)
    response = JSONResponse({'state': purpose})
    cookie(response, value)
    logger.info('Account security event=verification outcome=success')
    return response


@router.post('/api/account/password')
async def password(request: Request, body: Password):
    accounts = await mutation(request)
    await run_in_threadpool(accounts.set_password, nonce(request), owner(request), body.password.get_secret_value())
    response = JSONResponse({'state': 'signed_out', 'message': 'Password saved. Sign in with your verified email.'})
    response.delete_cookie(COOKIE, secure=True, httponly=True, samesite='lax', path='/')
    logger.info('Account security event=password outcome=success')
    return response


@router.post('/api/account/logout')
async def logout(request: Request):
    accounts = await mutation(request)
    await run_in_threadpool(accounts.logout, nonce(request), owner(request))
    response = JSONResponse({'state': 'signed_out'})
    response.delete_cookie(COOKIE, secure=True, httponly=True, samesite='lax', path='/')
    logger.info('Account security event=logout outcome=success')
    return response


@router.post('/api/account/recover', status_code=202)
async def recover(request: Request, body: Email):
    accounts = await mutation(request, recovery=True, email=body.email)
    await run_in_threadpool(accounts.recover, body.email)
    return {'message': 'If this email is eligible, check your inbox for a recovery email. Delivery may take a few minutes.'}
