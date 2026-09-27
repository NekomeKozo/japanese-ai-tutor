import asyncio
import time

from app.errors import TutorError
from app.llm.common import logger, request_path

ELIGIBLE = {'provider_timeout', 'provider_unavailable', 'provider_rate_limit'}


class FailoverProvider:
    """One primary attempt and at most one fallback inside the caller's deadline."""
    def __init__(self, primary, fallback, timeout):
        self.primary, self.fallback, self.timeout = primary, fallback, timeout

    async def generate(self, **kwargs):
        scope = request_path.get()
        if isinstance(scope, dict):
            if scope.get('_failover_primary_attempted'):
                raise TutorError('invalid_model_response', 'The tutor could not produce a valid response. Please try again.')
            scope['_failover_primary_attempted'] = True
        started = time.monotonic()
        try:
            # Reserve time for fallback; outer tutor/evaluator deadlines stay intact.
            async with asyncio.timeout(self.timeout * .50):
                return await self.primary.generate(**kwargs)
        except TimeoutError:
            reason = 'provider_timeout'
        except TutorError as exc:
            if exc.code not in ELIGIBLE and not exc.retryable_provider:
                raise
            reason = exc.code
        logger.info('primary_provider=gemini fallback_provider=groq fallback_triggered=true fallback_reason=%s', reason)
        try:
            remaining = max(.01, self.timeout * .95 - (time.monotonic() - started))
            async with asyncio.timeout(remaining):
                return await self.fallback.generate(**kwargs)
        except (TutorError, TimeoutError):
            raise TutorError('provider_unavailable', 'The AI providers are temporarily unavailable. Please try again later.', 503) from None
