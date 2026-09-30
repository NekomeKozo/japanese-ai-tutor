from uuid import UUID
from fastapi import APIRouter, Request
from app.conversation.catalog import SCENARIOS
from app.conversation.schemas import StartConversation
from app.errors import TutorError

router = APIRouter(prefix='/api', tags=['conversation practice'])


@router.get('/conversation/scenarios')
async def scenarios():
    return SCENARIOS


@router.post('/learners/{learner_id}/conversations', status_code=201)
async def start(learner_id: UUID, body: StartConversation, request: Request):
    owner = getattr(request.state, 'staging_identity', None) if request.app.state.settings.staging_access_enabled else None
    return request.app.state.conversations.start(learner_id, body, owner)


@router.get('/learners/{learner_id}/conversations/active')
async def active(learner_id: UUID, request: Request):
    return request.app.state.conversations.active(learner_id)


@router.get('/learners/{learner_id}/conversations/{session_id}')
async def detail(learner_id: UUID, session_id: UUID, request: Request):
    return request.app.state.conversations.get(learner_id, session_id)


@router.post('/learners/{learner_id}/conversations/{session_id}/finish')
async def finish(learner_id: UUID, session_id: UUID, request: Request):
    if session_id in request.app.state.tutor.saved_busy:
        raise TutorError('session_busy', 'Wait for the current reply before finishing.', 409)
    return request.app.state.conversations.finish(learner_id, session_id)
