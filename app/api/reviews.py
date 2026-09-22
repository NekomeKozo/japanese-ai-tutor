from uuid import UUID
from typing import Literal
from fastapi import APIRouter,Request,Query

router=APIRouter(prefix='/api/learners/{learner_id}/reviews')

@router.get('/due')
async def due(request:Request,learner_id:UUID,minutes:int=Query(20,ge=5,le=60),skill:Literal['grammar','vocabulary','kanji']|None=None):
    result=request.app.state.reviews.get_due_reviews(learner_id,minutes,skill)
    # Only exercise identities and user-facing timing; internal FSRS state stays private.
    for item in result['items']:
        for field in ('version','review_count'): item.pop(field,None)
    return result

@router.get('/forecast')
async def forecast(request:Request,learner_id:UUID,timezone:str=Query('UTC',max_length=100)):
    return request.app.state.reviews.forecast(learner_id,timezone)
