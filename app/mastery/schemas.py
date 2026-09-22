from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.mastery.policy import DIMENSIONS

Dimension = Literal['recognition', 'meaning', 'reading', 'production', 'understanding',
                    'application', 'on_reading', 'kun_reading']
EvidenceType = Literal['recognition', 'recall', 'comprehension', 'application', 'production']


class EvidenceContext(BaseModel):
    """Optional server-owned metadata; absent historical values remain unknown."""
    model_config = ConfigDict(extra='forbid')
    dimension: Dimension | None = None
    evidence_type: EvidenceType | None = None
    activity_type: str = Field(default='unknown', max_length=80)
    context_id: str | None = Field(default=None, max_length=128)
    hint_used: bool | None = None
    answer_revealed: bool = False
    learner_level: float | None = Field(default=None, ge=0, le=14)
    quality: float = Field(default=1, ge=0, le=1)
    reading_context: str | None = Field(default=None, max_length=80)


class Evidence(BaseModel):
    model_config = ConfigDict(extra='forbid', allow_inf_nan=False)
    event_id: str
    learner_id: str
    topic_id: str
    topic_type: Literal['vocabulary', 'grammar', 'kanji']
    dimension: Dimension
    score: float = Field(ge=0, le=1)
    difficulty: float = Field(ge=0, le=14)
    learner_level: float | None = Field(default=None, ge=0, le=14)
    evidence_type: EvidenceType
    activity_type: str
    source: str
    context_id: str
    hint_used: bool | None = None
    answer_revealed: bool = False
    quality: float = Field(ge=0, le=1)
    reading_context: str | None = None
    timestamp: datetime

    @model_validator(mode='after')
    def valid_dimension(self):
        if self.dimension not in DIMENSIONS[self.topic_type]:
            raise ValueError('Dimension not supported for this topic')
        if self.timestamp.tzinfo is None:
            raise ValueError('Evidence timestamps require timezone')
        return self
