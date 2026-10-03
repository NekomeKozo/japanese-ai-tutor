"""Small private-alpha controls; not production account authentication."""
import hashlib
import asyncio
import hmac
import json
import logging
import re
import time
import unicodedata
from collections import deque
from uuid import UUID, uuid4

from fastapi import APIRouter, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse
from pydantic import BaseModel, Field, SecretStr

from app.config import PROJECT_ROOT
from app.errors import TutorError

logger = logging.getLogger(__name__)
COOKIE = 'tutor_staging'
REDIRECT = "I'm designed specifically for Japanese learning. I can help with Japanese vocabulary, grammar, translation, conversation, JLPT preparation, or Japanese related to that topic."
router = APIRouter()


class WindowLimiter:
    def __init__(self):
        self.windows = {}

    def take(self, identity, limit, seconds=3600):
        now = time.monotonic()
        for key in list(self.windows):
            if not self.windows[key] or self.windows[key][-1] <= now - seconds:
                del self.windows[key]
        if identity not in self.windows and len(self.windows) >= 2000:
            raise TutorError('rate_limit', 'The service is busy. Please try again later.', 429)
        window = self.windows.setdefault(identity, deque())
        while window and window[0] <= now - seconds:
            window.popleft()
        if len(window) >= limit:
            logger.info('Request rejected category=rate_limit')
            raise TutorError('rate_limit', 'Please pause and try again later. The study request limit has been reached.', 429)
        window.append(now)


def sign_session(identity, settings):
    payload = f'{identity}.{int(time.time()) + settings.staging_session_hours * 3600}'
    signature = hmac.new(settings.staging_session_secret.get_secret_value().encode(), payload.encode(), hashlib.sha256).hexdigest()
    return f'{payload}.{signature}'


def read_session(token, settings, *, allow_expired=False):
    try:
        identity, expires, signature = token.split('.')
        UUID(identity)
        expected = hmac.new(settings.staging_session_secret.get_secret_value().encode(), f'{identity}.{expires}'.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, signature):
            return None
        if not allow_expired and int(expires) <= time.time():
            return None
        return identity
    except (ValueError, TypeError, AttributeError):
        return None


def initialize_access(repository):
    with repository.connection() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS staging_resources (
            kind TEXT NOT NULL, resource_id TEXT NOT NULL, owner_id TEXT NOT NULL,
            PRIMARY KEY(kind,resource_id))''')


def claim(request, kind, resource_id):
    if not request.app.state.settings.staging_access_enabled:
        return
    with request.app.state.repository.connection() as db:
        db.execute('INSERT INTO staging_resources VALUES (?,?,?)', (kind, str(resource_id), request.state.staging_identity))


def owned(request, kind, resource_id):
    try:
        UUID(str(resource_id))
    except ValueError:
        raise TutorError('invalid_request', 'A valid identifier is required.', 422) from None
    with request.app.state.repository.connection() as db:
        row = db.execute('SELECT owner_id FROM staging_resources WHERE kind=? AND resource_id=?', (kind, str(resource_id))).fetchone()
    if not row or row[0] != request.state.staging_identity:
        raise TutorError('not_found', 'This study resource is unavailable in your staging session.', 404)


async def protect_resources(request: Request):
    if not request.app.state.settings.staging_access_enabled or not request.url.path.startswith('/api/'):
        return
    params = request.path_params
    for name, kind in [('learner_id', 'learner'), ('assessment_id', 'assessment')]:
        if name in params:
            owned(request, kind, params[name])
    if request.url.path.startswith('/api/sessions/'):
        owned(request, 'session', params['session_id'])
    if request.url.path in ('/api/chat', '/api/curriculum/plan'):
        try:
            body = await request.json()
        except (ValueError, UnicodeDecodeError):
            raise TutorError('invalid_request', 'Send valid study data.', 422) from None
        if isinstance(body, dict):
            if body.get('learner_id'):
                owned(request, 'learner', body['learner_id'])
            if request.url.path == '/api/chat' and body.get('session_id'):
                owned(request, 'session', body['session_id'])


def check_scope(text, *, study_answer=False):
    text = unicodedata.normalize('NFKC', text).casefold()
    attacks = r'ignore\s+(?:all\s+)?(?:previous|prior|system|the)\s+(?:instructions|restrictions|rules)|(?:reveal|print|show|tell|give|repeat).{0,35}(?:system prompt|hidden instructions|api.?key|environment variables|database password)|(?:no longer|stop being).{0,20}japanese tutor|forget japanese|become chatgpt'
    scenario_override = r'\b(?:ignore|abandon|override)\b.{0,30}\b(?:scenario|roleplay)\b.{0,35}\b(?:become|act as|instead)\b'
    if re.search(attacks, text) or re.search(scenario_override, text):
        raise TutorError('scope_rejected', REDIRECT, 422)
    # A Japanese keyword appended to an unrelated command is not an allowance.
    unrelated = r'\b(?:write|create|debug|fix|build)\b.{0,45}\b(?:python (?:code|program|script)|(?:windows )?driver|history essay|business plan|javascript app)|\b(?:do|solve)\b.{0,30}\b(?:calculus|math)\b|stock picks|general therapist|explain quantum physics'
    language_goal = r'(?:in|into) japanese|japanese (?:for|vocabulary|language)|(?:translate|how (?:do|would) i (?:say|discuss|talk))'
    if re.search(unrelated, text) and not re.search(language_goal, text):
        raise TutorError('scope_rejected', REDIRECT, 422)
    if study_answer:
        return
    allowed = r'[\u3040-\u30ff\u3400-\u9fff]|\b(?:japanese|japan|grammar|vocabulary|kana|hiragana|katakana|kanji|keigo|jlpt|n[1-5]|translate|translation|honorifics|anime|manga|pronunciation|particle|romaji)\b|ordering food|\b(?:hi|hello|thanks|thank you|yes|no|again|why|explain more|another example|continue)\b'
    if not re.search(allowed, text):
        raise TutorError('scope_rejected', REDIRECT, 422)


def chat_has_exercise(request, body):
    """Allow short English answers only when the server has a pending exercise."""
    if body.learner_id and request.app.state.saved_sessions.exists(body.session_id):
        saved = request.app.state.saved_sessions.get(body.learner_id, body.session_id, 1)
        if saved.get('conversation') and saved['conversation']['status'] == 'active':
            from app.conversation.service import short_roleplay_answer
            return short_roleplay_answer(body.message)
        return bool(saved['turns'] and saved['turns'][-1]['response'].get('exercise'))
    session = request.app.state.memory.sessions.get(body.session_id)
    if session and session.messages and session.messages[-1].role == 'assistant':
        try:
            return bool(json.loads(session.messages[-1].content).get('exercise'))
        except (ValueError, AttributeError):
            return False
    return False


def study_guard(request, text=None, *, study_answer=False):
    settings = request.app.state.settings
    if settings.staging_access_enabled or settings.environment == 'staging':
        identity = getattr(request.state, 'staging_identity', None) or request.client.host
        request.app.state.ai_limiter.take(identity, settings.ai_rate_limit_per_hour)
        request.app.state.global_limiter.take('all', settings.ai_global_rate_limit_per_hour)
    if settings.scope_enforcement_enabled and text:
        check_scope(text, study_answer=study_answer)


async def before_request(request):
    settings = request.app.state.settings
    speech_upload = request.method == 'POST' and bool(re.fullmatch(r'/api/learners/[^/]+/speech/transcribe', request.url.path))
    # Authenticate speech uploads before buffering their larger body. Retain the
    # existing origin policy and learner ownership check, now before audio reads.
    if speech_upload and settings.staging_access_enabled:
        identity = read_session(request.cookies.get(COOKIE), settings)
        request.state.staging_identity = identity
        if not identity:
            return JSONResponse({'error': {'code': 'staging_access_required', 'message': 'Sign in to continue.'}}, status_code=401)
        origin = request.headers.get('origin')
        expected_origin = settings.frontend_url or str(request.base_url)
        if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and origin.rstrip('/') != expected_origin.rstrip('/')):
            return JSONResponse({'error': {'code': 'origin_rejected', 'message': 'Open the staging website to continue.'}}, status_code=403)
        try:
            owned(request, 'learner', request.url.path.split('/')[3])
        except TutorError as error:
            return JSONResponse({'error': {'code': error.code, 'message': error.message}}, status_code=error.status)
    if speech_upload:
        try:
            identity = getattr(request.state, 'staging_identity', None) or request.client.host
            request.app.state.speech_upload_limiter.take(identity, 10, 60)
        except TutorError as error:
            return JSONResponse({'error': {'code': error.code, 'message': error.message}}, status_code=error.status)
    # Only this exact speech route receives a larger allowance. No multipart
    # parser/spooled files: bounded raw WAV bytes, including false/chunked lengths.
    limit = 2 * 1024 * 1024 if speech_upload else 32768
    chunks, total = [], 0
    try:
        async with asyncio.timeout(15 if speech_upload else None):
            async for chunk in request.stream():
                total += len(chunk)
                if total > limit:
                    return JSONResponse({'error': {'code': 'request_too_large', 'message': 'Please send a shorter recording.' if speech_upload else 'Please send a shorter study request.'}}, status_code=413)
                chunks.append(chunk)
    except TimeoutError:
        return JSONResponse({'error': {'code': 'upload_timeout', 'message': 'The recording upload took too long. Please retry.'}}, status_code=408)
    request._body = b''.join(chunks)
    if not settings.staging_access_enabled:
        return None
    path = request.url.path
    identity = read_session(request.cookies.get(COOKIE), settings)
    request.state.staging_identity = identity
    if request.method not in ('GET', 'HEAD', 'OPTIONS'):
        # All browser mutations are same-origin; no wildcard credential CORS.
        origin = request.headers.get('origin')
        expected_origin = settings.frontend_url or str(request.base_url)
        if request.headers.get('sec-fetch-site') == 'cross-site' or (origin and origin.rstrip('/') != expected_origin.rstrip('/')):
            return JSONResponse({'error': {'code': 'origin_rejected', 'message': 'Open the staging website to continue.'}}, status_code=403)
    if path in ('/health', '/access', '/api/access', '/static/access.js', '/static/styles.css'):
        return None
    if not identity:
        if path == '/':
            return RedirectResponse('/access', status_code=303)
        return JSONResponse({'error': {'code': 'staging_access_required', 'message': 'Sign in to the private staging website to continue.'}}, status_code=401)
    return None


class AccessRequest(BaseModel):
    code: SecretStr = Field(max_length=512)


@router.get('/access', include_in_schema=False)
async def access_page():
    return FileResponse(PROJECT_ROOT / 'frontend' / 'access.html')


@router.post('/api/access', include_in_schema=False)
async def access(body: AccessRequest, request: Request):
    settings = request.app.state.settings
    if not settings.staging_access_enabled:
        raise TutorError('not_found', 'Staging access is not enabled.', 404)
    # A global cap also prevents circumventing the login cap by spoofing client IPs.
    request.app.state.login_limiter.take('global', 60, 600)
    request.app.state.login_client_limiter.take(request.client.host, 10, 600)
    if not hmac.compare_digest(body.code.get_secret_value().encode(), settings.staging_access_code.get_secret_value().encode()):
        raise TutorError('access_denied', 'The access code is incorrect.', 401)
    identity = read_session(request.cookies.get(COOKIE), settings, allow_expired=True) or str(uuid4())
    response = JSONResponse({'status': 'ok'})
    response.set_cookie(COOKIE, sign_session(identity, settings), httponly=True,
                        secure=settings.environment == 'staging', samesite='strict',
                        # Keep an expired signed identity so re-entering the code
                        # restores ownership. Authorization still expires server-side.
                        max_age=365 * 86400, path='/')
    return response
