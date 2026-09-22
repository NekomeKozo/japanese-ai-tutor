from typing import Literal
from uuid import UUID
from fastapi import APIRouter, Query, Request

router = APIRouter(prefix='/api/learners/{learner_id}/mastery')


@router.get('')
async def mastery(request: Request, learner_id: UUID,
    type: Literal['grammar','vocabulary','kanji'] | None = None,
    status: Literal['new','learning','developing','familiar','strong','needs_review'] | None = None,
    limit: int = Query(100, ge=1, le=100), offset: int = Query(0, ge=0, le=10000)):
    return request.app.state.mastery.list(learner_id, type, status, limit, offset)


@router.get('/{topic_id}')
async def topic(request: Request, learner_id: UUID, topic_id: str):
    service = request.app.state.mastery
    state = service.get_topic_mastery(learner_id, topic_id)
    state['history'] = service.get_recent_mastery_changes(learner_id, state['topic_id'])
    return state
