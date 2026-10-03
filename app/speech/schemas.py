from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field


class Transcript(BaseModel):
    request_id: UUID
    original_text: str = Field(min_length=1, max_length=4000)
    language: Literal['ja'] = 'ja'
    provider: Literal['groq'] = 'groq'
    duration_seconds: float = Field(gt=0, le=60)
