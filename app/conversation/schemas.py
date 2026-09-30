from typing import Literal
from pydantic import BaseModel, ConfigDict, Field
from app.tutor.schemas import Level

CorrectionPolicy = Literal['important_only', 'balanced', 'every_turn']


class Scenario(BaseModel):
    key: str
    title: str
    description: str
    learner_role: str
    tutor_role: str
    goal: str
    opening_line: str
    minimum_level: Level


class StartConversation(BaseModel):
    model_config = ConfigDict(extra='forbid')
    scenario_key: str = Field(min_length=1, max_length=60)
    correction_policy: CorrectionPolicy = 'balanced'
