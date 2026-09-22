import httpx

from app.config import Settings
from app.errors import TutorError
from app.llm.base import LLMProvider
from app.llm.openai import OpenAIProvider
from app.llm.gemini import GeminiProvider
from app.llm.common import DEFAULT_MODELS, logger, model_name


def provider_metadata(settings: Settings) -> dict:
    name = settings.llm_provider.strip().lower()
    if name not in PROVIDERS:
        return {'provider': 'unconfigured', 'model': None, 'api_key_present': False}
    try:
        model = model_name(settings.llm_model, DEFAULT_MODELS[name])
    except TutorError:
        model = None
    return {'provider': name, 'model': model,
            'api_key_present': bool(getattr(settings, PROVIDERS[name][1]).get_secret_value().strip())}


PROVIDERS = {'gemini': (GeminiProvider, 'gemini_api_key'), 'openai': (OpenAIProvider, 'openai_api_key')}


def configuration_issue(settings: Settings) -> str | None:
    provider = PROVIDERS.get(settings.llm_provider.strip().lower())
    if provider is None:
        return 'Set LLM_PROVIDER to gemini or openai and restart the server.'
    if not getattr(settings, provider[1]).get_secret_value().strip():
        return f'Set {provider[1].upper()} in .env and restart the server to begin.'
    try:
        model_name(settings.llm_model, 'default')
    except TutorError as exc:
        return exc.message
    return None


class UnconfiguredProvider:
    def __init__(self, message: str, code: str = 'provider_configuration'):
        self.message = message
        self.code = code

    async def generate(self, **kwargs) -> str:
        logger.warning('LLM failure category=%s', self.code)
        raise TutorError(self.code, self.message, 503)


def create_provider(settings: Settings, client: httpx.AsyncClient) -> LLMProvider:
    issue = configuration_issue(settings)
    if issue:
        entry = PROVIDERS.get(settings.llm_provider.strip().lower())
        code = 'missing_api_key' if entry and not getattr(settings, entry[1]).get_secret_value().strip() else 'provider_configuration'
        logger.warning('LLM configuration issue category=%s', code)
        return UnconfiguredProvider(issue, code)
    adapter, _ = PROVIDERS[settings.llm_provider.strip().lower()]
    return adapter(settings, client)
