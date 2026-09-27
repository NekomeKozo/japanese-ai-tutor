"""Groq chat-completions adapter. The application still validates every schema."""
import re

import httpx

from app.errors import TutorError
from app.llm.common import checked_generation, log_http_failure


def groq_model(settings):
    model = settings.groq_model.strip()
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._/-]{0,199}', model) or '..' in model:
        raise TutorError('provider_configuration', 'Set GROQ_MODEL to a supported model ID on the server.', 503)
    return model


class GroqProvider:
    def __init__(self, settings, client):
        self.settings, self.client = settings, client

    @checked_generation('groq')
    async def generate(self, *, instructions, messages, schema=None):
        key = self.settings.groq_api_key.get_secret_value().strip()
        if not key:
            raise TutorError('missing_api_key', 'Configure the fallback provider on the server.', 503)
        model = groq_model(self.settings)
        payload = {
            'model': model,
            'messages': [{'role': 'system', 'content': instructions},
                         *[{'role': m.role, 'content': m.content} for m in messages]],
            'max_completion_tokens': self.settings.llm_max_output_tokens,
            'stream': False,
        }
        if schema is not None:
            payload['response_format'] = {'type': 'json_schema', 'json_schema': {
                'name': 'japanese_tutor', 'strict': False, 'schema': schema}}
        try:
            response = await self.client.post('https://api.groq.com/openai/v1/chat/completions',
                headers={'Authorization': f'Bearer {key}'}, json=payload,
                timeout=self.settings.llm_timeout_seconds)
        except httpx.TimeoutException:
            raise TutorError('provider_timeout', 'The tutor took too long. Please try again.', 504) from None
        except httpx.RequestError:
            raise TutorError('provider_unavailable', 'The AI provider is unavailable. Please try later.', 503) from None
        log_http_failure('groq', model, response)
        if response.status_code in (401, 403):
            raise TutorError('provider_auth', 'Check fallback provider configuration on the server.', 503)
        if response.status_code == 429:
            raise TutorError('provider_rate_limit', 'The AI provider is busy. Please try later.', 503)
        if response.is_error:
            raise TutorError('provider_failure', 'The AI provider could not complete this request.', 502)
        try:
            choice = response.json()['choices'][0]
            if choice['message'].get('refusal') or choice.get('finish_reason') == 'content_filter':
                raise TutorError('provider_refusal', 'Try a different Japanese learning question.')
            if choice.get('finish_reason') != 'stop':
                raise TutorError('incomplete_response', 'The tutor response was incomplete. Please try again.')
            content = choice['message']['content']
            if not isinstance(content, str) or not content.strip():
                raise ValueError('Empty response')
            return content
        except (ValueError, KeyError, IndexError, TypeError, AttributeError):
            raise TutorError('invalid_model_response', 'The tutor returned an unreadable response. Please try again.') from None
