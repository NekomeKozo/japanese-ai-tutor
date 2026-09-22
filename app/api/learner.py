from uuid import UUID

from fastapi import APIRouter, Query, Request

from app.learner.schemas import PreferencesPatch

router = APIRouter(prefix='/api/learners', tags=['learner memory'])


@router.post('', status_code=201)
async def create(request: Request):
    return request.app.state.learners.create()


@router.get('/{learner_id}/profile')
async def profile(learner_id: UUID, request: Request):
    return request.app.state.learners.profile(learner_id)


@router.patch('/{learner_id}/preferences')
async def preferences(learner_id: UUID, body: PreferencesPatch, request: Request):
    return request.app.state.learners.preferences(learner_id, body)


@router.get('/{learner_id}/activity')
async def activity(learner_id: UUID, request: Request, limit: int = Query(20, ge=1, le=50), offset: int = Query(0, ge=0, le=10000)):
    return request.app.state.learners.activity(learner_id, limit, offset)


@router.post('/{learner_id}/sessions', status_code=201)
async def create_session(learner_id: UUID, request: Request):
    return request.app.state.saved_sessions.create(learner_id)


@router.get('/{learner_id}/sessions')
async def sessions(learner_id: UUID, request: Request, limit: int = Query(20, ge=1, le=50)):
    return request.app.state.saved_sessions.list(learner_id, limit)


@router.get('/{learner_id}/sessions/{session_id}')
async def session(learner_id: UUID, session_id: UUID, request: Request):
    return request.app.state.saved_sessions.get(learner_id, session_id)


@router.post('/{learner_id}/sessions/{session_id}/close')
async def close_session(learner_id: UUID, session_id: UUID, request: Request):
    request.app.state.saved_sessions.close(learner_id, session_id)
    return {'closed': True}
