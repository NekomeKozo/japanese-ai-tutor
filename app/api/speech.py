from uuid import UUID
import logging

from fastapi import APIRouter, Header, Request

from app.speech.provider import configuration_issue
from app.speech.schemas import Transcript

router = APIRouter(prefix='/api')


@router.get('/speech/config')
async def speech_config(request: Request):
    issue = configuration_issue(request.app.state.settings)
    return {'enabled': issue is None, 'provider': 'groq', 'setup_message': issue}


@router.post('/learners/{learner_id}/speech/transcribe', response_model=Transcript)
async def transcribe(learner_id: UUID, request: Request, x_transcription_id: UUID = Header()):
    # Global ownership dependency already checked the learner; never persist audio.
    request.app.state.learners.profile(learner_id)
    identity = getattr(request.state, 'staging_identity', None) or request.client.host
    result = await request.app.state.speech.transcribe(identity=identity, request_id=x_transcription_id,
        audio=await request.body(), content_type=request.headers.get('content-type', ''))
    logging.getLogger('uvicorn.error').info('STT success provider=groq duration_ms=%d', round(result.duration_seconds * 1000))
    return result
