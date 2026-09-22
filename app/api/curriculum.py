from uuid import UUID

from fastapi import APIRouter, Request

from app.curriculum.schemas import CompletionRequest, PlanRequest

router=APIRouter(tags=['curriculum'])
PREFIX='/api/learners/{learner_id}/study'


@router.post('/api/curriculum/plan')
async def plan(body:PlanRequest,request:Request):
    return request.app.state.curriculum.create(body)


@router.get(PREFIX+'/active')
async def active(learner_id:UUID,request:Request):
    return request.app.state.curriculum.active(learner_id)


@router.get(PREFIX+'/{session_id}')
async def session(learner_id:UUID,session_id:UUID,request:Request):
    return request.app.state.curriculum.get(learner_id,session_id)


@router.post(PREFIX+'/{session_id}/start')
async def start(learner_id:UUID,session_id:UUID,request:Request):
    return request.app.state.curriculum.start(learner_id,session_id)


@router.post(PREFIX+'/{session_id}/activities/{activity_id}/open')
async def open_activity(learner_id:UUID,session_id:UUID,activity_id:UUID,request:Request):
    return await request.app.state.curriculum.open_activity(learner_id,session_id,activity_id)


@router.post(PREFIX+'/{session_id}/activities/{activity_id}/complete')
async def complete_activity(learner_id:UUID,session_id:UUID,activity_id:UUID,body:CompletionRequest,request:Request):
    return await request.app.state.curriculum.complete_activity(learner_id,session_id,activity_id,body)


@router.post(PREFIX+'/{session_id}/activities/{activity_id}/skip')
async def skip_activity(learner_id:UUID,session_id:UUID,activity_id:UUID,request:Request):
    return request.app.state.curriculum.skip(learner_id,session_id,activity_id)


@router.post(PREFIX+'/{session_id}/complete')
async def complete(learner_id:UUID,session_id:UUID,request:Request):
    return request.app.state.curriculum.finish(learner_id,session_id)


@router.post(PREFIX+'/{session_id}/abandon')
async def abandon(learner_id:UUID,session_id:UUID,request:Request):
    return request.app.state.curriculum.finish(learner_id,session_id,abandon=True)
