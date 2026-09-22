from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

Mode = Literal['chat', 'correct', 'grammar', 'vocabulary', 'examples', 'exercise', 'quiz']
Level = Literal['beginner', 'N5', 'N4', 'N3', 'N2', 'N1']


class StrictModel(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)


class Evaluation(StrictModel):
    status: Literal['incorrect', 'understandable_but_incorrect', 'acceptable_but_unnatural', 'correct', 'natural']
    correct: bool
    natural: bool


class Correction(StrictModel):
    original: str = Field(min_length=1, max_length=4000)
    improved: str = Field(min_length=1, max_length=4000)


class Exercise(StrictModel):
    kind: Literal['exercise', 'quiz']
    question: str = Field(min_length=1, max_length=2000)
    hint: str | None = Field(max_length=1000)
    choices: list[str] = Field(max_length=6)


class TutorResponse(StrictModel):
    # All keys are required; nullable fields allow non-evaluation teaching turns.
    message: str = Field(min_length=1, max_length=6000)
    evaluation: Evaluation | None
    correction: Correction | None
    explanation: str | None = Field(max_length=6000)
    examples: list[str] = Field(max_length=6)
    detected_topics: list[str] = Field(max_length=12)
    exercise: Exercise | None

    @field_validator('message')
    @classmethod
    def nonblank_message(cls, value: str) -> str:
        if not value.strip():
            raise ValueError('Tutor message cannot be blank.')
        return value


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    session_id: UUID
    message: str = Field(min_length=1, max_length=4000)
    mode: Mode = 'chat'
    level: Level = 'beginner'
    learner_id: UUID | None = None
    request_id: UUID | None = None

    @field_validator('message')
    @classmethod
    def clean_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError('Enter a message before sending.')
        return value


class ChatResponse(BaseModel):
    session_id: UUID
    response: TutorResponse
