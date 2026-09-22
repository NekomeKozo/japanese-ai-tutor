import httpx

from app.config import Settings
from app.errors import TutorError
from app.llm.base import Message
from app.llm.common import DEFAULT_MODELS, checked_generation, log_http_failure, model_name


class OpenAIProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client

    @checked_generation('openai')
    async def generate(self, *, instructions: str, messages: list[Message], schema: dict | None = None) -> str:
        key = self.settings.openai_api_key.get_secret_value().strip()
        if not key:
            raise TutorError('missing_api_key', 'Set OPENAI_API_KEY in .env and restart the server.', 503)
        model = model_name(self.settings.llm_model, DEFAULT_MODELS['openai'])
        try:
            response = await self.client.post(
                'https://api.openai.com/v1/responses',
                headers={'Authorization': f'Bearer {key}'},
                json={
                    'model': model,
                    'instructions': instructions,
                    'input': [{'role': item.role, 'content': item.content} for item in messages],
                    'text': {'format': {'type': 'json_schema', 'name': 'tutor_response',
                                        'strict': True, 'schema': schema}} if schema is not None else {'format': {'type': 'text'}},
                    'max_output_tokens': self.settings.llm_max_output_tokens,
                    'store': False,
                },
                timeout=self.settings.llm_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise TutorError('provider_timeout', 'The tutor took too long to respond. Please try again.', 504) from exc
        except httpx.RequestError as exc:
            raise TutorError('provider_unavailable', 'Cannot reach the AI provider. Please try again.', 503) from exc

        log_http_failure('openai', model, response)
        if response.status_code in (401, 403):
            raise TutorError('provider_auth', 'Check the API key and model access on the server.', 503)
        if response.status_code == 429:
            raise TutorError('provider_rate_limit', 'The AI provider is busy or its quota was reached. Try later or check your API account.', 503)
        if response.is_error:
            raise TutorError('provider_failure', 'The AI provider could not complete this request. Check your model configuration or try again.')
        try:
            data = response.json()
            if data.get('status') != 'completed':
                raise TutorError('incomplete_response', 'The tutor response was incomplete. Please try again.')
            texts = []
            for item in data['output']:
                if item.get('type') != 'message':
                    continue
                for part in item['content']:
                    if part.get('type') == 'refusal':
                        raise TutorError('provider_refusal', 'The tutor could not answer that request. Try a different Japanese learning question.')
                    if part.get('type') == 'output_text':
                        texts.append(part['text'])
            output = ''.join(texts)
            if not output.strip():
                raise ValueError('Empty response')
            return output
        except (ValueError, KeyError, TypeError, AttributeError) as exc:
            raise TutorError('invalid_model_response', 'The tutor returned an unreadable response. Please try again.') from exc
