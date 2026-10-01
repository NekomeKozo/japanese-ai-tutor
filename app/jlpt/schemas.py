from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator
from app.assessment.evaluator import normalize
from app.learner.catalog import TOPICS

Level = Literal['N5', 'N4']
Section = Literal['vocabulary', 'kanji', 'grammar', 'reading']
Mode = Literal['quick', 'standard', 'focused', 'weakness', 'mock']
TYPES = {
    'vocabulary': {'vocabulary_meaning', 'vocabulary_usage'},
    'kanji': {'kanji_reading', 'kanji_meaning'},
    'grammar': {'grammar_choice', 'sentence_completion', 'grammar_usage'},
    'reading': {'reading_comprehension'},
}


class Strict(BaseModel):
    model_config = ConfigDict(extra='forbid', hide_input_in_errors=True)


class Question(Strict):
    id: str = Field(pattern=r'^jlpt_[a-z0-9_]{3,70}$')
    level: Level
    section: Section
    question_type: str
    prompt: str = Field(min_length=1, max_length=1800)
    choices: list[str] = Field(default_factory=list, max_length=4)
    answers: list[str] = Field(min_length=1, max_length=4)
    explanation: str = Field(min_length=1, max_length=1400)
    topic_id: str = Field(max_length=80)
    difficulty: float = Field(ge=0, le=14, allow_inf_nan=False)
    status: Literal['candidate', 'reviewed', 'approved', 'retired']
    source_type: Literal['application_authored', 'rag_candidate']
    version: int = Field(default=1, ge=1)
    passage_id: str | None = Field(default=None, max_length=80)
    passage_text: str | None = Field(default=None, max_length=2500)
    reading_context: str | None = Field(default=None, max_length=80)
    dimension: Literal['recognition', 'meaning', 'reading', 'understanding', 'on_reading', 'kun_reading'] = 'recognition'

    @model_validator(mode='after')
    def validate_content(self):
        if self.question_type not in TYPES[self.section]:
            raise ValueError('Question type does not match section')
        if self.topic_id not in TOPICS or self.topic_id.startswith('other_'):
            raise ValueError('Question requires a known learning topic')
        if TOPICS[self.topic_id].skill != self.section:
            raise ValueError('Learning topic must match the question section')
        from app.mastery.policy import DIMENSIONS
        if self.section in DIMENSIONS and self.dimension not in DIMENSIONS[self.section]:
            raise ValueError('Invalid mastery dimension for this section')
        if not self.prompt.strip() or not self.explanation.strip():
            raise ValueError('Prompt and explanation cannot be blank')
        if any(not a.strip() or len(a) > 300 for a in [*self.choices, *self.answers]):
            raise ValueError('Invalid answer length')
        if len({normalize(a) for a in self.answers}) != len(self.answers):
            raise ValueError('Duplicate accepted answers')
        if self.choices:
            if len(self.choices) < 2 or len({normalize(c) for c in self.choices}) != len(self.choices):
                raise ValueError('Choices must be distinct')
            if len(self.answers) != 1 or self.answers[0] not in self.choices:
                raise ValueError('Exactly one approved choice is required')
        elif self.question_type != 'kanji_reading':
            raise ValueError('Only fixed kanji readings may omit choices')
        if self.section == 'reading' and not (self.passage_id and self.passage_text and self.passage_text.strip()):
            raise ValueError('Reading questions require a passage')
        if self.dimension in ('on_reading', 'kun_reading') and not self.reading_context:
            raise ValueError('A contextual kanji reading is required')
        return self

    def public(self):
        return self.model_dump(include={'id', 'level', 'section', 'question_type', 'prompt', 'choices', 'passage_text'})


class Start(Strict):
    level: Level = 'N5'
    section: Literal['mixed', 'vocabulary', 'kanji', 'grammar', 'reading'] = 'mixed'
    mode: Mode = 'quick'
    question_count: Literal[5, 10, 20] | None = None
    timed: bool = False
    request_id: UUID

    @model_validator(mode='after')
    def selection(self):
        if self.mode == 'focused' and self.section == 'mixed':
            raise ValueError('Focused practice needs a section')
        if self.mode == 'mock' and self.section != 'mixed':
            raise ValueError('Mock practice uses mixed sections')
        return self


class Answer(Strict):
    submission_id: UUID
    question_id: str = Field(min_length=1, max_length=80)
    answer: str = Field(min_length=1, max_length=300)
