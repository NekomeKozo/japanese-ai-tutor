from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

SessionType = Literal['balanced','review','new_material','grammar','vocabulary','kanji','reading','sentence_construction','quick_practice']
Focus = Literal['grammar','vocabulary','kanji','reading','sentence_construction','hiragana','katakana']


class PlanRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    learner_id: UUID
    available_minutes: int = Field(default=30, ge=5, le=60, strict=True)
    session_type: SessionType = 'balanced'
    requested_focus: Focus | None = None


class CompletionRequest(BaseModel):
    model_config = ConfigDict(extra='forbid')
    submission_id: UUID
    answer: str = Field(min_length=1, max_length=4000)

    @field_validator('answer')
    @classmethod
    def nonblank(cls, value):
        if not value.strip(): raise ValueError('Enter an answer or skip the activity')
        return value.strip()


class PlanStrategy(BaseModel):
    model_config=ConfigDict(extra='forbid')
    name: Literal['balanced','review_heavy','progression','goal_focused','quick_session']
    target_review_ratio: float=Field(ge=0,le=1)
    returning_learner: bool
    review_ratio: float=Field(ge=0,le=1)
    new_ratio: float=Field(ge=0,le=1)


class PlannedActivity(BaseModel):
    model_config=ConfigDict(extra='forbid')
    activity_id: UUID
    order: int=Field(ge=1,le=7)
    topic_id: str=Field(min_length=1,max_length=80)
    title: str=Field(min_length=1,max_length=160)
    skill: Focus
    activity_type: Literal['guided_practice','vocabulary_review','kanji_recognition','reading_comprehension','sentence_construction','multiple_choice']
    difficulty: float=Field(ge=0,le=14)
    duration_minutes: int=Field(ge=2,le=12)
    purpose: Literal['review','new_material']
    reason_codes: list[str]=Field(min_length=1,max_length=8)
    reason: str=Field(min_length=1,max_length=250)
    focus_dimension: Literal['production','reading','on_reading','kun_reading','application','meaning','recognition','understanding'] | None = None
    review_schedule_id: UUID | None = None
    review_version: int | None = Field(default=None,ge=1)
    review_variant: int = Field(default=0,ge=0)
    reteach: bool = False


class StudyPlan(BaseModel):
    model_config=ConfigDict(extra='forbid')
    available_minutes: int=Field(ge=5,le=60)
    estimated_minutes: int=Field(ge=2,le=60)
    strategy: PlanStrategy
    note: str=Field(min_length=1,max_length=600)
    activities: list[PlannedActivity]=Field(min_length=1,max_length=7)

    @model_validator(mode='after')
    def consistent(self):
        if sum(a.duration_minutes for a in self.activities)!=self.estimated_minutes or self.estimated_minutes>self.available_minutes:
            raise ValueError('Invalid plan time budget')
        if [a.order for a in self.activities]!=list(range(1,len(self.activities)+1)):
            raise ValueError('Invalid activity order')
        if len({a.topic_id for a in self.activities})!=len(self.activities): raise ValueError('Duplicate topic in plan')
        if abs(self.strategy.review_ratio+self.strategy.new_ratio-1)>.001: raise ValueError('Invalid plan balance')
        return self


class Lesson(BaseModel):
    model_config = ConfigDict(extra='forbid', strict=True)
    topic_id: str = Field(min_length=1,max_length=80)
    difficulty: float = Field(ge=0,le=14)
    title: str = Field(min_length=1,max_length=160)
    explanation: str = Field(min_length=1,max_length=2500)
    examples: list[str] = Field(max_length=3)
    prompt: str = Field(min_length=1,max_length=2000)
    choices: list[str] = Field(max_length=4)
    answers: list[str] = Field(min_length=1,max_length=3)
    evaluation: Literal['choice','semantic','fixed']
    reading_context: str | None = Field(default=None,max_length=80)
    feedback: str = Field(min_length=1,max_length=1200)

    @model_validator(mode='after')
    def consistent(self):
        if any(not text.strip() or len(text)>1000 for text in self.examples+self.choices+self.answers):
            raise ValueError('Blank or oversized lesson field')
        if self.evaluation == 'choice' and (len(self.choices)<2 or len(set(self.choices))!=len(self.choices) or any(a not in self.choices for a in self.answers)):
            raise ValueError('Invalid choice answer')
        if self.evaluation == 'semantic' and self.choices: raise ValueError('Unexpected choices')
        return self

    def public(self):
        return self.model_dump(exclude={'answers','evaluation','feedback'})
