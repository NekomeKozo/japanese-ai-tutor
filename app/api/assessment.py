from uuid import UUID

from fastapi import APIRouter, Request

from app.assessment.schemas import AnswerRequest, StartRequest
from app.errors import TutorError

router = APIRouter(prefix='/api/assessments', tags=['placement'])


@router.post('', status_code=201)
async def start(body: StartRequest, request: Request):
    return request.app.state.assessment.start(body)


@router.get('/{assessment_id}')
async def resume(assessment_id: UUID, request: Request):
    engine = request.app.state.assessment
    return engine.public(engine.load(assessment_id))


@router.post('/{assessment_id}/answers')
async def answer(assessment_id: UUID, body: AnswerRequest, request: Request):
    return await request.app.state.assessment.answer(assessment_id, body)


@router.get('/{assessment_id}/result')
async def result(assessment_id: UUID, request: Request):
    state = request.app.state.assessment.load(assessment_id)
    if not state.profile:
        raise TutorError('assessment_incomplete', 'Finish the assessment before requesting its result.', 409)
    return state.profile
