from uuid import UUID

from fastapi import APIRouter, Request

from app.assessment.schemas import AnswerRequest, StartRequest
from app.errors import TutorError
from app.safeguards import claim, study_guard
from app.safeguards import guard_profile_creation
from starlette.concurrency import run_in_threadpool

router = APIRouter(prefix='/api/assessments', tags=['placement'])


@router.post('', status_code=201)
async def start(body: StartRequest, request: Request):
    await run_in_threadpool(guard_profile_creation, request)
    result = request.app.state.assessment.start(body)
    claim(request, 'assessment', result['assessment_id'])
    claim(request, 'learner', result['learner_id'])
    return result


@router.get('/{assessment_id}')
async def resume(assessment_id: UUID, request: Request):
    engine = request.app.state.assessment
    return engine.public(engine.load(assessment_id))


@router.post('/{assessment_id}/answers')
async def answer(assessment_id: UUID, body: AnswerRequest, request: Request):
    study_guard(request, body.answer, study_answer=True)
    return await request.app.state.assessment.answer(assessment_id, body)


@router.get('/{assessment_id}/result')
async def result(assessment_id: UUID, request: Request):
    state = request.app.state.assessment.load(assessment_id)
    if not state.profile:
        raise TutorError('assessment_incomplete', 'Finish the assessment before requesting its result.', 409)
    return state.profile
