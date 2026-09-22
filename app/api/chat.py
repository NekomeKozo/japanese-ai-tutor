from uuid import UUID

from fastapi import APIRouter, Request, Response

from app.llm.factory import configuration_issue, provider_metadata
from app.tutor.schemas import ChatRequest, ChatResponse

router = APIRouter(prefix='/api')


@router.get('/health')
async def health(request: Request):
    issue = configuration_issue(request.app.state.settings)
    return {'status': 'ok', 'provider_configured': issue is None, 'setup_message': issue,
            **provider_metadata(request.app.state.settings)}


@router.post('/sessions', status_code=201)
async def create_session(request: Request):
    return {'session_id': str(request.app.state.memory.create())}


@router.delete('/sessions/{session_id}', status_code=204)
async def delete_session(session_id: UUID, request: Request):
    request.app.state.memory.delete(session_id)
    return Response(status_code=204)


@router.post('/chat', response_model=ChatResponse)
async def chat(body: ChatRequest, request: Request):
    return await request.app.state.tutor.chat(body)
