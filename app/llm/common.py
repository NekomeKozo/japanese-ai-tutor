"""Safe adapter diagnostics and syntax checks, independent of learning schemas."""
from functools import wraps
from contextvars import ContextVar
import json
import logging
import re
import time

from app.errors import TutorError

# Inherit Uvicorn's configured INFO handler so safe provider diagnostics are
# visible under the documented deployment command, without enabling HTTP bodies.
logger = logging.getLogger('uvicorn.error.llm')
request_path = ContextVar('llm_request_path', default='direct')
DEFAULT_MODELS = {'gemini': 'gemini-3.1-flash-lite', 'openai': 'gpt-4.1-mini'}


def current_request_path():
    scope = request_path.get()
    return getattr(scope.get('route'), 'path', 'unmatched') if isinstance(scope, dict) else scope


def log_http_failure(provider, model, response):
    """Log allowlisted metadata, never raw vendor messages (which may echo input)."""
    if not response.is_error:
        return
    status, reason = 'unknown', 'unknown'
    try:
        error = response.json().get('error', {})
        candidate = error.get('status', error.get('type'))
        if candidate in {'INVALID_ARGUMENT', 'NOT_FOUND', 'PERMISSION_DENIED', 'UNAUTHENTICATED',
                         'RESOURCE_EXHAUSTED', 'UNAVAILABLE', 'INTERNAL', 'FAILED_PRECONDITION',
                         'invalid_request_error', 'server_error', 'insufficient_quota'}:
            status = candidate
        for detail in error.get('details', []):
            if detail.get('reason') in {'API_KEY_INVALID', 'API_KEY_EXPIRED', 'API_KEY_SERVICE_BLOCKED',
                                       'API_KEY_HTTP_REFERRER_BLOCKED', 'API_KEY_IP_ADDRESS_BLOCKED',
                                       'SERVICE_DISABLED', 'BILLING_DISABLED', 'CONSUMER_INVALID'}:
                reason = detail['reason']
    except (ValueError, TypeError, AttributeError):
        pass
    summary = {400: 'request or schema rejected', 401: 'authentication rejected',
               403: 'access denied', 404: 'model or endpoint unavailable',
               429: 'rate limit or quota reached'}.get(response.status_code,
                    'provider service unavailable' if response.status_code >= 500 else 'request failed')
    logger.warning('LLM HTTP failure provider=%s model=%s http_status=%s provider_type=%s reason=%s path=%s summary=%s',
                   provider, model, response.status_code, status, reason, current_request_path(), summary)


def model_name(configured: str, default: str) -> str:
    model = configured.strip() or default
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,199}', model):
        raise TutorError('provider_configuration', 'Set LLM_MODEL to a model ID, not a URL, and restart.', 503)
    return model


def checked_generation(provider: str):
    def decorate(generate):
        @wraps(generate)
        async def checked(self, **kwargs):
            started = time.monotonic()
            try:
                output = await generate(self, **kwargs)
                if kwargs.get('schema') is not None:
                    try:
                        json.loads(output)
                    except (ValueError, TypeError) as exc:
                        raise TutorError('invalid_model_response', 'The tutor returned an unreadable response. Please try again.') from exc
                logger.info('LLM success provider=%s path=%s latency_ms=%d',
                            provider, current_request_path(), int((time.monotonic() - started) * 1000))
                return output
            except TutorError as exc:
                # Never include exceptions, request/response bodies, headers or prompts.
                logger.warning('LLM failure provider=%s category=%s path=%s', provider, exc.code, current_request_path())
                raise
        return checked
    return decorate
