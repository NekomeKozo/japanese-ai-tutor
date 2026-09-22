from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

Skill = Literal['hiragana', 'katakana', 'vocabulary', 'grammar', 'particles',
                'verb_conjugation', 'adjective_conjugation', 'kanji', 'reading', 'sentence_construction']
SKILLS = ('hiragana', 'katakana', 'vocabulary', 'grammar', 'particles', 'verb_conjugation',
          'adjective_conjugation', 'kanji', 'reading', 'sentence_construction')
MAJORS = ('hiragana', 'katakana', 'vocabulary', 'grammar', 'kanji', 'reading', 'sentence_construction')
GRAMMAR_PARTS = ('particles', 'verb_conjugation', 'adjective_conjugation')
SCRIPTS = ('hiragana', 'katakana')
QuestionType = Literal['multiple_choice', 'vocabulary_meaning', 'japanese_to_english',
    'english_to_japanese', 'sentence_completion', 'grammar_selection', 'kanji_reading',
    'kanji_meaning', 'reading_comprehension', 'sentence_construction']


class Model(BaseModel):
    model_config = ConfigDict(extra='forbid')


class Question(Model):
    id: str
    skill: Skill
    topic: str
    difficulty: float = Field(ge=0, le=14)
    jlpt_reference: str | None
    question_type: QuestionType
    prompt: str = Field(min_length=1, max_length=4000)
    choices: list[str] = Field(default_factory=list, max_length=6)
    answers: list[str] = Field(min_length=1)
    romaji_answers: list[str] = Field(default_factory=list)
    explanation: str
    evaluation: Literal['choice', 'fixed', 'semantic']
    source: Literal['curated', 'generated'] = 'curated'

    @model_validator(mode='after')
    def valid_item(self):
        if not all(answer.strip() for answer in self.answers):
            raise ValueError('Empty answer key')
        if self.evaluation == 'choice' and (len(self.choices) < 2 or
                len(set(self.choices)) != len(self.choices) or any(a not in self.choices for a in self.answers)):
            raise ValueError('Choice questions need distinct choices and a valid key')
        if self.evaluation != 'choice' and self.choices:
            raise ValueError('Only choice evaluation uses choices')
        if self.skill in SCRIPTS and self.difficulty > 2:
            raise ValueError('Script scale is 0–2')
        return self

    def public(self) -> dict:
        return self.model_dump(include={'id', 'skill', 'question_type', 'prompt', 'choices'})


class SemanticEvaluation(Model):
    model_config = ConfigDict(extra='forbid', strict=True)
    score: float = Field(ge=0, le=1)
    meaning_correct: bool
    grammar_correct: bool
    naturalness: float = Field(ge=0, le=1)
    acceptable_alternative: bool
    feedback_internal: str = Field(min_length=1, max_length=1500)
    detected_errors: list[str] = Field(max_length=8)


class Evaluation(Model):
    score: float | None = Field(default=None, ge=0, le=1)
    weight: float = Field(default=1, ge=0, le=1)
    method: Literal['deterministic', 'llm', 'dont_know', 'unavailable']
    romaji_used: bool = False
    detail: SemanticEvaluation | None = None


class Evidence(Model):
    question: Question
    answer: str | None
    submission_id: UUID
    dont_know: bool
    evaluation: Evaluation


class SkillEstimate(Model):
    difficulty_estimate: float | None
    estimated_level: str
    recognition_score: float | None = None
    evidence_count: int
    unavailable_count: int
    confidence: float
    interval: list[float] | None = None
    ceiling_reached: bool = False


class LearnerProfile(Model):
    schema_version: int = 1
    learner_id: UUID
    assessment_id: UUID
    created_at: float
    overall_estimate: str
    overall_score: float | None
    probable_study_range: str
    confidence: float
    confidence_label: Literal['Low', 'Moderate', 'High']
    skills: dict[str, SkillEstimate]
    strong_topics: list[str]
    weak_topics: list[str]
    recommended_starting_point: str
    stopping_reason: str
    questions_answered: int
    limitations: list[str]
    listening: None = None
    speaking: None = None


class AssessmentState(Model):
    schema_version: int = 1
    bank_version: str = 'phase2-v1'
    assessment_id: UUID
    learner_id: UUID
    status: Literal['in_progress', 'completed'] = 'in_progress'
    self_report: Literal['beginner', 'some', 'N5', 'N4', 'unknown'] = 'unknown'
    started_at: float
    updated_at: float
    completed_at: float | None = None
    version: int = 0
    current: Question | None = None
    evidence: list[Evidence] = Field(default_factory=list)
    profile: LearnerProfile | None = None


class StartRequest(Model):
    self_report: Literal['beginner', 'some', 'N5', 'N4', 'unknown'] = 'unknown'


class AnswerRequest(Model):
    question_id: str = Field(min_length=1, max_length=80)
    submission_id: UUID
    answer: str | None = Field(default=None, max_length=4000)
    dont_know: bool = False

    @model_validator(mode='after')
    def valid_answer(self):
        if self.dont_know:
            if self.answer is not None:
                raise ValueError('Do not supply an answer with dont_know')
        elif self.answer is None or not self.answer.strip():
            raise ValueError('Supply an answer or choose I don’t know')
        if self.answer is not None:
            self.answer = self.answer.strip()
        return self
