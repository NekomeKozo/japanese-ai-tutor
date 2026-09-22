from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.assessment.schemas import Skill
from app.tutor.schemas import Level, TutorResponse


class Preferences(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    romaji_enabled: bool = False
    furigana_enabled: bool = True
    explanation_language: Literal['english', 'japanese', 'balanced'] = 'english'
    correction_style: Literal['gentle', 'balanced', 'strict'] = 'balanced'
    preferred_difficulty: Level | None = None
    primary_goal: Literal['general', 'travel', 'conversation', 'university', 'work', 'JLPT_N5', 'JLPT_N4', 'JLPT_N3', 'JLPT_N2', 'JLPT_N1'] = 'general'


class PreferencesPatch(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    romaji_enabled: bool | None = None
    furigana_enabled: bool | None = None
    explanation_language: Literal['english', 'japanese', 'balanced'] | None = None
    correction_style: Literal['gentle', 'balanced', 'strict'] | None = None
    preferred_difficulty: Level | None = None
    primary_goal: Literal['general', 'travel', 'conversation', 'university', 'work', 'JLPT_N5', 'JLPT_N4', 'JLPT_N3', 'JLPT_N2', 'JLPT_N1'] | None = None

    @model_validator(mode='after')
    def non_null(self):
        if any(getattr(self, name) is None for name in self.model_fields_set - {'preferred_difficulty'}):
            raise ValueError('Only preferred_difficulty can be null')
        return self


class LearningObservation(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    event_type: Literal['performance', 'concept_explained', 'requested_help']
    skill: Skill
    topic_key: str = Field(min_length=1, max_length=80)
    score: float | None = Field(ge=0, le=1)
    difficulty: float | None = Field(ge=0, le=14)
    error_tags: list[str] = Field(max_length=5)

    @model_validator(mode='after')
    def valid_score(self):
        if (self.event_type == 'performance') != (self.score is not None):
            raise ValueError('Only performance observations have a score')
        return self


class ObservedTutorResponse(TutorResponse):
    learning_observations: list[LearningObservation] = Field(max_length=8)


class LearningEvent(BaseModel):
    model_config = ConfigDict(extra='forbid')
    event_id: UUID
    learner_id: UUID
    event_type: Literal['performance', 'concept_explained', 'requested_help']
    topic_key: str = Field(min_length=1, max_length=80)
    skill: Skill
    score: float | None = Field(default=None, ge=0, le=1)
    difficulty: float | None = Field(default=None, ge=0, le=14)
    source: Literal['tutor_chat', 'quiz', 'exercise', 'manual_review', 'placement_assessment', 'curriculum']
    error_tags: list[str] = Field(default_factory=list, max_length=5)

    @model_validator(mode='after')
    def score_matches_type(self):
        if (self.event_type == 'performance') != (self.score is not None):
            raise ValueError('Only performance events have a score')
        return self
