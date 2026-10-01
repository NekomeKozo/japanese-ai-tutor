from uuid import UUID
from fastapi import APIRouter, Request
from app.jlpt.schemas import Start, Answer

router=APIRouter(prefix='/api',tags=['JLPT practice'])

@router.get('/jlpt/catalog')
def catalog(request: Request):
    return request.app.state.jlpt.bank.catalog()

@router.post('/learners/{learner_id}/jlpt/sessions',status_code=201)
def create(learner_id: UUID, body: Start, request: Request):
    return request.app.state.jlpt.start(learner_id,body)

@router.get('/learners/{learner_id}/jlpt/sessions/active')
def active(learner_id: UUID,request: Request):
    return request.app.state.jlpt.active(learner_id)

@router.get('/learners/{learner_id}/jlpt/sessions/{session_id}')
def get(learner_id: UUID,session_id: UUID,request: Request):
    return request.app.state.jlpt.get(learner_id,session_id)

@router.post('/learners/{learner_id}/jlpt/sessions/{session_id}/answer')
def answer(learner_id: UUID,session_id: UUID,body: Answer,request: Request):
    return request.app.state.jlpt.answer(learner_id,session_id,body)

@router.post('/learners/{learner_id}/jlpt/sessions/{session_id}/finish')
def finish(learner_id: UUID,session_id: UUID,request: Request):
    return request.app.state.jlpt.finish(learner_id,session_id)

@router.post('/learners/{learner_id}/jlpt/sessions/{session_id}/abandon')
def abandon(learner_id: UUID,session_id: UUID,request: Request):
    return request.app.state.jlpt.finish(learner_id,session_id,abandon=True)

@router.get('/learners/{learner_id}/jlpt/history')
def history(learner_id: UUID,request: Request):
    return request.app.state.jlpt.history(learner_id)

@router.post('/learners/{learner_id}/jlpt/sessions/{session_id}/explanations/{question_id}')
def explanation(learner_id: UUID,session_id: UUID,question_id: str,request: Request):
    return request.app.state.jlpt.explanation(learner_id,session_id,question_id)
