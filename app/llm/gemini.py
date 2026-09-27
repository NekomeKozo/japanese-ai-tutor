"""Google Gemini generateContent REST adapter; no provider objects escape here."""
import httpx

from app.config import Settings
from app.errors import TutorError
from app.llm.base import Message
from app.llm.common import DEFAULT_MODELS, checked_generation, log_http_failure, model_name


class GeminiProvider:
    def __init__(self, settings: Settings, client: httpx.AsyncClient):
        self.settings = settings
        self.client = client

    @checked_generation('gemini')
    async def generate(self, *, instructions: str, messages: list[Message], schema: dict | None = None) -> str:
        key = self.settings.gemini_api_key.get_secret_value().strip()
        if not key:
            raise TutorError('missing_api_key', 'Set GEMINI_API_KEY in .env and restart the server.', 503)
        model = model_name(self.settings.llm_model, DEFAULT_MODELS['gemini'])
        generation = {'maxOutputTokens': self.settings.llm_max_output_tokens, 'candidateCount': 1}
        if schema is not None:
            generation.update(responseMimeType='application/json', responseJsonSchema=schema)
        # This model supports disabling thinking; reserve the existing small output
        # budget for the answer. Do not send model-specific options to other models.
        if model == 'gemini-2.5-flash':
            generation['thinkingConfig'] = {'thinkingBudget': 0}
        try:
            response = await self.client.post(
                f'https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent',
                headers={'x-goog-api-key': key},
                json={
                    'systemInstruction': {'parts': [{'text': instructions}]},
                    'contents': [{'role': 'model' if item.role == 'assistant' else 'user',
                                  'parts': [{'text': item.content}]} for item in messages],
                    'generationConfig': generation,
                },
                timeout=self.settings.llm_timeout_seconds,
            )
        except httpx.TimeoutException as exc:
            raise TutorError('provider_timeout', 'The tutor took too long to respond. Please try again.', 504) from exc
        except httpx.RequestError as exc:
            raise TutorError('provider_unavailable', 'Cannot reach the AI provider. Please try again.', 503) from exc
        log_http_failure('gemini', model, response)
        if response.status_code in (401, 403):
            raise TutorError('provider_auth', 'Check the API key and model access on the server.', 503)
        if response.status_code == 429:
            raise TutorError('provider_rate_limit', 'The AI provider is busy or its quota was reached. Try later or check your API account.', 503)
        if response.status_code == 404:
            raise TutorError('provider_failure', 'The configured AI model is unavailable. Check LLM_MODEL on the server and restart.')
        if response.status_code >= 500:
            raise TutorError('provider_failure', 'The AI provider is temporarily unavailable. Please try again shortly.', retryable_provider=True)
        if response.is_error:
            raise TutorError('provider_failure', 'The AI provider could not complete this request. Check your model configuration or try again.')
        try:
            data = response.json()
            if data.get('promptFeedback', {}).get('blockReason'):
                raise TutorError('provider_refusal', 'The tutor could not answer that request. Try a different Japanese learning question.')
            candidate = data['candidates'][0]
            finish = candidate.get('finishReason')
            if finish in {'SAFETY', 'RECITATION', 'BLOCKLIST', 'PROHIBITED_CONTENT', 'SPII', 'IMAGE_SAFETY'}:
                raise TutorError('provider_refusal', 'The tutor could not answer that request. Try a different Japanese learning question.')
            if finish != 'STOP':
                raise TutorError('incomplete_response', 'The tutor response was incomplete. Please try again.')
            output = ''.join(part['text'] for part in candidate['content']['parts']
                             if 'text' in part and not part.get('thought', False))
            if not output.strip():
                raise ValueError('Empty response')
            return output
        except (ValueError, KeyError, IndexError, TypeError, AttributeError) as exc:
            raise TutorError('invalid_model_response', 'The tutor returned an unreadable response. Please try again.') from exc
