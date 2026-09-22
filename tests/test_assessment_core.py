import asyncio
from uuid import uuid4

import pytest

from app.assessment.evaluator import AnswerEvaluator
from app.assessment.questions import QuestionBank
from app.assessment.schemas import AnswerRequest, AssessmentState, Evidence, Evaluation
from app.assessment.scoring import estimate
from app.assessment.selector import select_question


def evidence(question, score, **kwargs):
    return Evidence(question=question, answer='test', submission_id=uuid4(), dont_know=False,
                    evaluation=Evaluation(score=score, method='deterministic', **kwargs))


def test_bank_is_valid_and_balanced():
    bank = QuestionBank.load()
    assert 40 <= len(bank.items) <= 80
    assert len({q.id for q in bank.items}) == len(bank.items)
    assert len({q.skill for q in bank.items}) == 10
    assert max(q.difficulty for q in bank.items) == 14
    for question in bank.items:
        assert not {'answers', 'difficulty', 'explanation', 'jlpt_reference'} & question.public().keys()


def test_local_evaluation_never_calls_provider():
    class NoLLM:
        async def generate(self, **kwargs):
            raise AssertionError('Do not call provider')
    question = QuestionBank.load().items[0]
    evaluator = AnswerEvaluator(NoLLM(), 1)
    correct = AnswerRequest(question_id=question.id, submission_id=uuid4(), answer=question.answers[0])
    assert asyncio.run(evaluator.evaluate(question, correct)).score == 1
    wrong = next(c for c in question.choices if c not in question.answers)
    assert asyncio.run(evaluator.evaluate(question, correct.model_copy(update={'answer': wrong}))).score == 0
    result = asyncio.run(evaluator.evaluate(question, AnswerRequest(question_id=question.id, submission_id=uuid4(), dont_know=True)))
    assert result.score == 0 and result.weight < 1


def test_difficulty_and_partial_credit_affect_estimates():
    questions = [q for q in QuestionBank.load().items if q.skill == 'vocabulary']
    easy, hard = questions[1], questions[4]
    assert estimate('vocabulary', [evidence(hard, 1)]).difficulty_estimate > estimate('vocabulary', [evidence(easy, 1)]).difficulty_estimate
    scores = [estimate('vocabulary', [evidence(easy, score)]).difficulty_estimate for score in (0, .25, .5, .75, 1)]
    assert scores == sorted(scores) and len(set(scores)) == 5
    assert estimate('reading', [evidence(hard, 1)]).difficulty_estimate is None


def test_selector_no_repeat_and_script_screen():
    bank = QuestionBank.load()
    state = AssessmentState(assessment_id=uuid4(), learner_id=uuid4(), started_at=0, updated_at=0)
    for _ in range(12):
        question = select_question(state, bank)
        assert question.id not in {e.question.id for e in state.evidence}
        state.evidence.append(evidence(question, 1))
    assert [e.question.skill for e in state.evidence[:4]] == ['hiragana', 'hiragana', 'katakana', 'katakana']
    assert len({e.question.skill for e in state.evidence}) == 10
