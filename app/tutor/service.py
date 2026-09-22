import asyncio
import json

from pydantic import ValidationError

from app.config import Settings
from app.assessment.repository import AssessmentRepository
from app.learner.context import build_context, observation_instructions, preference_instructions
from app.learner.observations import extract_observations
from app.learner.schemas import ObservedTutorResponse
from app.errors import TutorError
from app.llm.base import LLMProvider, Message
from app.memory.conversation import ConversationStore
from app.tutor.prompts import build_instructions, format_request
from app.tutor.schemas import ChatRequest, ChatResponse, TutorResponse


def parse_response(raw: str) -> TutorResponse:
    if not isinstance(raw, str) or len(raw) > 24000:
        raise TutorError('invalid_model_response', 'The tutor returned an invalid response. Please try again.')
    try:
        return TutorResponse.model_validate_json(raw)
    except (ValidationError, ValueError) as exc:
        raise TutorError('invalid_model_response', 'The tutor returned an invalid response. Please try again.') from exc


class TutorService:
    def __init__(self, provider: LLMProvider, memory: ConversationStore, settings: Settings,
                 profiles: AssessmentRepository | None = None, learners=None, saved_sessions=None):
        self.provider, self.memory, self.settings = provider, memory, settings
        self.profiles = profiles
        self.learners, self.saved_sessions = learners, saved_sessions
        self.saved_busy = set()

    def learner_instructions(self, request, *, observe=False):
        profile = self.learners.profile(request.learner_id)
        prefs = profile['preferences']
        level = prefs['preferred_difficulty']
        if level is None:
            level = next((n for n in ('N1', 'N2', 'N3', 'N4', 'N5') if n in profile['estimated_level']), 'beginner')
        instructions = build_instructions(level, prefs['romaji_enabled'])
        instructions += '\nApplication placement evidence and current learning memory (provisional): ' + build_context(profile)
        instructions += preference_instructions(profile)
        if observe:
            instructions += observation_instructions()
        return instructions

    async def persistent_chat(self, request):
        if request.request_id is None:
            raise TutorError('request_id_required', 'Saved conversations require a request_id UUID for safe retries.', 422)
        if request.session_id in self.saved_busy:
            raise TutorError('session_busy', 'Wait for the current reply before sending another message.', 409)
        self.saved_busy.add(request.session_id)
        try:
            replay = self.saved_sessions.replay(request)
            if replay:
                return ChatResponse(session_id=request.session_id, response=replay)
            saved = self.saved_sessions.get(request.learner_id, request.session_id, self.settings.max_history_turns)
            if saved['ended_at'] is not None:
                raise TutorError('session_closed', 'This saved conversation has ended. Start a new conversation.', 409)
            messages = self.saved_sessions.history(saved, self.settings.max_history_turns)
            messages.append(Message('user', format_request(request.mode, request.message)))
            try:
                async with asyncio.timeout(self.settings.llm_timeout_seconds):
                    raw = await self.provider.generate(instructions=self.learner_instructions(request, observe=True),
                        messages=messages, schema=ObservedTutorResponse.model_json_schema())
            except TimeoutError as exc:
                raise TutorError('provider_timeout', 'The tutor took too long to respond. Please try again.', 504) from exc
            if not isinstance(raw, str) or len(raw) > 30000:
                raise TutorError('invalid_model_response', 'The tutor returned an invalid response. Please try again.')
            try:
                teaching, observations = extract_observations(raw)
            except (ValueError, TypeError) as exc:
                raise TutorError('invalid_model_response', 'The tutor returned an invalid response. Please try again.') from exc
            reply = parse_response(teaching)
            reply = self.saved_sessions.commit(request, reply, observations, saved['version'])
            return ChatResponse(session_id=request.session_id, response=reply)
        finally:
            self.saved_busy.discard(request.session_id)

    async def chat(self, request: ChatRequest) -> ChatResponse:
        if request.learner_id is not None and self.saved_sessions is not None and self.saved_sessions.exists(request.session_id):
            return await self.persistent_chat(request)
        with self.memory.use(request.session_id) as session:
            if request.learner_id is not None:
                if session.learner_id is not None and session.learner_id != request.learner_id:
                    raise TutorError('session_learner_conflict', 'Start a new session when switching learners.', 409)
                session.learner_id = request.learner_id
            user = Message('user', format_request(request.mode, request.message))
            instructions = build_instructions(request.level, self.settings.romaji_enabled)
            if request.learner_id is not None and self.learners is not None:
                instructions = self.learner_instructions(request)
            elif request.learner_id is not None and self.profiles is not None:
                profile = self.profiles.profile(request.learner_id)
                summary = profile.model_dump(mode='json', include={'overall_estimate', 'confidence_label',
                    'strong_topics', 'weak_topics', 'recommended_starting_point'})
                instructions += ('\nApplication placement evidence (provisional, never official certification): '
                    + json.dumps(summary, ensure_ascii=False) + '\nUse this evidence to choose a starting difficulty and '
                    'review focus, while respecting explicit learner requests. Do not invent unmeasured abilities.')
            try:
                async with asyncio.timeout(self.settings.llm_timeout_seconds):
                    raw = await self.provider.generate(
                        instructions=instructions,
                        messages=[*session.messages, user],
                        schema=TutorResponse.model_json_schema(),
                    )
            except TimeoutError as exc:
                raise TutorError('provider_timeout', 'The tutor took too long to respond. Please try again.', 504) from exc
            reply = parse_response(raw)
            self.memory.append_turn(session, user, Message('assistant', reply.model_dump_json()))
            return ChatResponse(session_id=request.session_id, response=reply)
