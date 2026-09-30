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
from app.knowledge.service import GROUNDING_INSTRUCTIONS
from app.knowledge.service import source_dump_request
from app.conversation.service import instructions as conversation_instructions, teaching_question


def parse_response(raw: str) -> TutorResponse:
    if not isinstance(raw, str) or len(raw) > 24000:
        raise TutorError('invalid_model_response', 'The tutor returned an invalid response. Please try again.')
    try:
        return TutorResponse.model_validate_json(raw)
    except (ValidationError, ValueError) as exc:
        raise TutorError('invalid_model_response', 'The tutor returned an invalid response. Please try again.') from exc


class TutorService:
    def __init__(self, provider: LLMProvider, memory: ConversationStore, settings: Settings,
                 profiles: AssessmentRepository | None = None, learners=None, saved_sessions=None, knowledge=None):
        self.provider, self.memory, self.settings = provider, memory, settings
        self.profiles = profiles
        self.learners, self.saved_sessions = learners, saved_sessions
        self.saved_busy = set()
        self.knowledge = knowledge

    async def grounding(self, request, instructions, messages, *, roleplay=False):
        if self.knowledge is None or not self.settings.knowledge_enabled:
            return instructions, messages, None
        if roleplay and not teaching_question(request.message) and not source_dump_request(request.message):
            return instructions + GROUNDING_INSTRUCTIONS, messages, None
        context = await self.knowledge.context_for(request.message, request.mode)
        return instructions + GROUNDING_INSTRUCTIONS, self.knowledge.messages(messages, context), context

    def validate_grounding(self, reply, context):
        if context is not None:
            self.knowledge.check_response(reply, context)

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
            saved = self.saved_sessions.get(request.learner_id, request.session_id, self.settings.max_history_turns)
            practice = saved.get('conversation')
            if practice:
                request = request.model_copy(update={'mode': 'chat'})
            replay = self.saved_sessions.replay(request)
            if replay:
                return ChatResponse(session_id=request.session_id, response=replay)
            if saved['ended_at'] is not None:
                raise TutorError('session_closed', 'This saved conversation has ended. Start a new conversation.', 409)
            messages = self.saved_sessions.history(saved, self.settings.max_history_turns)
            if practice and not messages:
                messages.append(Message('assistant', practice['scenario']['opening_line']))
            messages.append(Message('user', format_request(request.mode, request.message)))
            instructions = self.learner_instructions(request, observe=True)
            if practice:
                instructions += conversation_instructions(practice)
            instructions, messages, grounding = await self.grounding(request,
                instructions, messages, roleplay=bool(practice))
            try:
                async with asyncio.timeout(self.settings.llm_timeout_seconds):
                    raw = await self.provider.generate(instructions=instructions,
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
            if practice:
                reply = reply.model_copy(update={'exercise': None})
                # English help and explicit explanations are not evidence of Japanese performance.
                import re
                if teaching_question(request.message) or not re.search(r'[\u3040-\u30ff\u3400-\u9fff]', request.message):
                    observations = [item for item in observations if item.event_type != 'performance']
            self.validate_grounding(reply, grounding)
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
            instructions, messages, grounding = await self.grounding(request, instructions, [*session.messages, user])
            try:
                async with asyncio.timeout(self.settings.llm_timeout_seconds):
                    raw = await self.provider.generate(
                        instructions=instructions,
                        messages=messages,
                        schema=TutorResponse.model_json_schema(),
                    )
            except TimeoutError as exc:
                raise TutorError('provider_timeout', 'The tutor took too long to respond. Please try again.', 504) from exc
            reply = parse_response(raw)
            self.validate_grounding(reply, grounding)
            self.memory.append_turn(session, user, Message('assistant', reply.model_dump_json()))
            return ChatResponse(session_id=request.session_id, response=reply)
