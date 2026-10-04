from app.api.audio_progress import router as audio_progress_router
from app.audio_progress.service import AudioProgressService
import logging
from contextlib import asynccontextmanager
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.middleware.gzip import GZipMiddleware
from app.web_assets import WebAssets
from starlette.exceptions import HTTPException

from app.api.chat import router
from app.api.assessment import router as assessment_router
from app.api.learner import router as learner_router
from app.api.curriculum import router as curriculum_router
from app.api.mastery import router as mastery_router
from app.api.reviews import router as review_router
from app.api.conversation import router as conversation_router
from app.api.jlpt import router as jlpt_router
from app.api.speech import router as speech_router
from app.speech.provider import GroqSpeechProvider, SpeechProvider
from app.speech.service import SpeechService
from app.jlpt.bank import Bank as JLPTBank
from app.jlpt.service import JLPTService
from app.conversation.service import ConversationService
from app.review.service import ReviewService
from app.mastery.service import MasteryService
from app.curriculum.service import CurriculumService
from app.learner.service import LearnerService
from app.learner.sessions import SessionService
from app.assessment.engine import AssessmentEngine
from app.assessment.evaluator import AnswerEvaluator
from app.assessment.questions import QuestionBank
from app.assessment.repository import AssessmentRepository
from app.config import ENV_FILE, Settings
from app.errors import TutorError
from app.llm.base import LLMProvider
from app.llm.factory import create_provider, provider_metadata
from app.llm.common import request_path
from app.memory.conversation import ConversationStore
from app.tutor.service import TutorService
from app.knowledge.repository import KnowledgeRepository
from app.knowledge.service import KnowledgeService
from app.safeguards import (router as access_router, before_request, protect_resources,
                            initialize_access, WindowLimiter)

FRONTEND = Path(__file__).resolve().parent.parent / 'frontend'
logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, provider: LLMProvider | None = None,
               speech_provider: SpeechProvider | None = None) -> FastAPI:
    settings = settings or Settings()
    assets = WebAssets(FRONTEND)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        async with httpx.AsyncClient() as client:
            app.state.settings = settings
            app.state.memory = ConversationStore(max_sessions=settings.max_sessions,
                max_turns=settings.max_history_turns, ttl=settings.session_ttl_seconds)
            llm = provider or create_provider(settings, client)
            metadata = provider_metadata(settings)
            logging.getLogger('uvicorn.error').info(
                'Tutor runtime environment=%s database_backend=%s provider=%s model=%s api_key_present=%s',
                settings.environment, 'postgresql' if settings.database_url.get_secret_value() else 'sqlite',
                metadata['provider'], metadata['model'], metadata['api_key_present'])
            try:
                bank = QuestionBank.load()
            except (ValueError, OSError):
                if settings.environment == 'staging':
                    raise RuntimeError('The built-in placement question bank is missing or invalid.') from None
                logger.error('Assessment question bank is invalid; ordinary chat remains available')
                bank = QuestionBank([])
            repository = AssessmentRepository(settings.assessment_db_path, settings.database_url.get_secret_value())
            app.state.repository = repository
            try:
                repository.initialize(bank)
                if settings.staging_access_enabled:
                    initialize_access(repository)
            except TutorError:
                if settings.environment == 'staging' or settings.staging_access_enabled:
                    raise RuntimeError('Staging storage initialization failed; check database configuration.') from None
                logger.error('Assessment database initialization failed; ordinary chat remains available')
            app.state.ai_limiter = WindowLimiter()
            app.state.global_limiter = WindowLimiter()
            app.state.login_limiter = WindowLimiter()
            app.state.login_client_limiter = WindowLimiter()
            app.state.speech_upload_limiter = WindowLimiter()
            app.state.speech_uploads = 0
            app.state.speech = SpeechService(settings, speech_provider or GroqSpeechProvider(settings, client))
            app.state.assessment = AssessmentEngine(repository, bank,
                AnswerEvaluator(llm, settings.llm_timeout_seconds), settings.assessment_ttl_seconds)
            app.state.learners = LearnerService(repository)
            app.state.audio_progress = AudioProgressService(repository)
            app.state.mastery = MasteryService(repository)
            app.state.reviews = ReviewService(repository)
            app.state.jlpt = JLPTService(repository, JLPTBank.load())
            app.state.saved_sessions = SessionService(repository)
            app.state.conversations = ConversationService(repository, app.state.saved_sessions)
            app.state.saved_sessions.conversations = app.state.conversations
            app.state.curriculum = CurriculumService(repository,app.state.learners,llm,
                AnswerEvaluator(llm,settings.llm_timeout_seconds),settings.llm_timeout_seconds)
            app.state.tutor = TutorService(llm, app.state.memory, settings, repository,
                app.state.learners, app.state.saved_sessions,
                knowledge=KnowledgeService(KnowledgeRepository(settings.knowledge_db_path,
                    settings.database_url.get_secret_value()), settings))
            yield
            app.state.memory.sessions.clear()

    app = FastAPI(title='GoiGrow — Japanese Tutor', version='0.6.5', lifespan=lifespan,
                  dependencies=[Depends(protect_resources)],
                  docs_url=None if settings.environment == 'staging' else '/docs',
                  redoc_url=None if settings.environment == 'staging' else '/redoc',
                  openapi_url=None if settings.environment == 'staging' else '/openapi.json')
    app.state.web_assets = assets

    def secure_response(request, response):
        response.headers['Cache-Control'] = assets.cache_control(request, response.status_code)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['Permissions-Policy'] = 'camera=(), geolocation=(), microphone=(self)'
        if settings.environment == 'staging':
            response.headers['Strict-Transport-Security'] = 'max-age=15552000'
        # Only the actual development documentation needs its external scripts.
        docs = settings.environment != 'staging' and request.url.path in ('/docs', '/docs/oauth2-redirect', '/redoc')
        if not docs:
            response.headers['Content-Security-Policy'] = "default-src 'self'; script-src 'self'; worker-src 'self'; manifest-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; media-src blob:; frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'"
        return response

    @app.middleware('http')
    async def response_headers(request: Request, call_next):
        # Route templates exclude query strings, learner IDs and user-supplied paths.
        # Routing populates this scope before the service calls its provider.
        token = request_path.set(request.scope)
        speech_upload = request.method == 'POST' and request.url.path.endswith('/speech/transcribe')
        speech_busy = speech_upload and request.app.state.speech_uploads >= 2
        if speech_upload and not speech_busy:
            request.app.state.speech_uploads += 1
        try:
            response = (JSONResponse({'error': {'code': 'stt_busy', 'message': 'Transcription is busy. Please retry shortly.'}}, status_code=429)
                        if speech_busy else await before_request(request))
            if response is None:
                response = await call_next(request)
        finally:
            request_path.reset(token)
            if speech_upload and not speech_busy:
                request.app.state.speech_uploads -= 1
        return secure_response(request, response)

    @app.exception_handler(TutorError)
    async def tutor_error(request: Request, exc: TutorError):
        return JSONResponse(status_code=exc.status, content={'error': {'code': exc.code, 'message': exc.message}})

    @app.exception_handler(RequestValidationError)
    async def validation_error(request: Request, exc: RequestValidationError):
        message = ('Check the assessment ID, question, submission ID, and answer (up to 4,000 characters), or choose I don’t know.'
            if request.url.path.startswith('/api/assessments') else
            'Send a nonempty message of up to 4,000 characters, a valid session, learning mode and level.')
        if request.url.path.startswith('/api/learners'):
            message = 'Check the learner/session identifiers and supported preference values.'
        if request.url.path.endswith('/speech/transcribe'):
            message = 'Send a valid learner identifier and transcription request identifier.'
        if request.url.path.startswith('/api/curriculum') or '/study/' in request.url.path:
            message = 'Check the learner/session/activity identifiers, study time (5–60 minutes), focus and answer.'
        return JSONResponse(status_code=422, content={'error': {'code': 'invalid_request',
            'message': message}})

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, exc: HTTPException):
        return JSONResponse(status_code=exc.status_code, content={'error': {'code': 'http_error', 'message': 'This route or method is unavailable.'}})

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, exc: Exception):
        logger.error('Unexpected backend exception: %s', type(exc).__name__)
        return secure_response(request, JSONResponse(status_code=500, content={'error': {'code': 'internal_error',
            'message': 'Something went wrong. Please try again.'}}))

    app.include_router(access_router)
    app.include_router(router)
    app.include_router(assessment_router)
    app.include_router(learner_router)
    app.include_router(curriculum_router)
    app.include_router(mastery_router)
    app.include_router(review_router)
    app.include_router(conversation_router)
    app.include_router(jlpt_router)
    app.include_router(speech_router)
    app.include_router(audio_progress_router)
    # Compress authored static content only. Private API/audio responses stay untouched.
    app.mount('/static', GZipMiddleware(StaticFiles(directory=FRONTEND), minimum_size=500, compresslevel=6), name='static')

    @app.get('/manifest.webmanifest', include_in_schema=False)
    async def manifest():
        return JSONResponse(assets.manifest(), media_type='application/manifest+json')

    @app.get('/service-worker.js', include_in_schema=False)
    async def service_worker():
        return Response(assets.worker, media_type='application/javascript', headers={'Service-Worker-Allowed':'/'})

    @app.get('/offline', include_in_schema=False)
    async def offline():
        return HTMLResponse(assets.offline)

    @app.get('/favicon.ico', include_in_schema=False)
    async def favicon():
        return FileResponse(FRONTEND / 'pwa/favicon.ico', media_type='image/x-icon')

    @app.get('/health', include_in_schema=False)
    async def health():
        return {'status': 'ok'}

    @app.get('/ready', include_in_schema=False)
    async def ready(request: Request):
        request.app.state.repository.require_ready()
        with request.app.state.repository.connection() as db:
            db.execute('SELECT 1').fetchone()
        return {'status': 'ready'}

    @app.get('/', include_in_schema=False)
    async def index():
        return HTMLResponse(assets.index)

    return app


app = create_app()
