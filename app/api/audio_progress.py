from uuid import UUID
from fastapi import APIRouter, Request
from pydantic import BaseModel, ConfigDict, Field

router = APIRouter(prefix='/api/learners/{learner_id}/audio', tags=['audio activity'])


class StartAttempt(BaseModel):
    model_config = ConfigDict(extra='forbid')
    attempt_id: UUID
    exercise_id: str = Field(min_length=1, max_length=80)


class CompleteAttempt(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    choice: int | None = Field(default=None, ge=0, le=5)
    assisted: bool = False
    transcription_id: UUID | None = Field(default=None, strict=False)


@router.post('/attempts', status_code=201)
async def start(learner_id: UUID, body: StartAttempt, request: Request):
    return request.app.state.audio_progress.start(learner_id, body)


@router.post('/attempts/{attempt_id}/complete')
async def complete(learner_id: UUID, attempt_id: UUID, body: CompleteAttempt, request: Request):
    return request.app.state.audio_progress.complete(learner_id, attempt_id, body)


@router.get('/progress')
async def progress(learner_id: UUID, request: Request):
    return request.app.state.audio_progress.progress(learner_id)
