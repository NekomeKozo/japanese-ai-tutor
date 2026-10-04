from starlette.concurrency import run_in_threadpool
from uuid import UUID
from typing import Literal
from fastapi import APIRouter,Request,Query
from pydantic import BaseModel, ConfigDict, Field
from app.safeguards import study_guard

router=APIRouter(prefix='/api/learners/{learner_id}/reviews')

class RecallSubmission(BaseModel):
    model_config = ConfigDict(extra='forbid')
    submission_id: UUID
    version: int = Field(ge=1, strict=True)
    rating: Literal['again','hard','good','easy']

@router.get('/flashcards')
async def flashcards(request:Request,learner_id:UUID,minutes:int=Query(20,ge=5,le=60)):
    return await run_in_threadpool(request.app.state.reviews.get_flashcards, learner_id,minutes)

@router.post('/{review_id}/recall')
async def recall(request:Request,learner_id:UUID,review_id:UUID,body:RecallSubmission):
    study_guard(request)
    return await run_in_threadpool(request.app.state.reviews.recall, learner_id,review_id,body.submission_id,body.version,body.rating)

@router.get('/history')
async def history(request:Request,learner_id:UUID,limit:int=Query(20,ge=1,le=50)):
    return await run_in_threadpool(request.app.state.reviews.history, learner_id,limit)

@router.get('/due')
async def due(request:Request,learner_id:UUID,minutes:int=Query(20,ge=5,le=60),skill:Literal['grammar','vocabulary','kanji']|None=None):
    result=await run_in_threadpool(request.app.state.reviews.get_due_reviews, learner_id,minutes,skill)
    # Only exercise identities and user-facing timing; internal FSRS state stays private.
    for item in result['items']:
        for field in ('version','review_count'): item.pop(field,None)
    return result

@router.get('/forecast')
async def forecast(request:Request,learner_id:UUID,timezone:str=Query('UTC',max_length=100)):
    return await run_in_threadpool(request.app.state.reviews.forecast, learner_id,timezone)
