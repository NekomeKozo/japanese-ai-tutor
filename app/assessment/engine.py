import logging
import time
from uuid import UUID, uuid4

from app.assessment.evaluator import AnswerEvaluator
from app.assessment.questions import BANK_VERSION, QuestionBank
from app.assessment.repository import AssessmentRepository
from app.assessment.results import build_profile
from app.assessment.schemas import AnswerRequest, AssessmentState, Evidence, MAJORS, SCRIPTS, StartRequest
from app.assessment.scoring import all_estimates, beginner_screen, overall_confidence, evidence_for
from app.assessment.selector import select_question
from app.errors import TutorError

logger = logging.getLogger(__name__)
MIN_QUESTIONS, MAX_QUESTIONS = 16, 30


def stopping_reason(state: AssessmentState) -> str | None:
    if beginner_screen(state.evidence):
        return 'beginner_screen'
    if len(state.evidence) >= MAX_QUESTIONS:
        return 'maximum_questions'
    skills = all_estimates(state.evidence)
    if len(state.evidence) < MIN_QUESTIONS or any(skills[s].evidence_count < 2 for s in MAJORS):
        return None
    for skill in MAJORS:
        if skill in SCRIPTS:
            continue
        observations = [e for e in evidence_for(skill, state.evidence) if e.evaluation.score is not None]
        bounded = any(e.evaluation.score >= .65 for e in observations) and any(e.evaluation.score < .65 for e in observations)
        floor = any(e.question.difficulty == 0 and e.evaluation.score < .4 for e in observations)
        if not bounded and not skills[skill].ceiling_reached and not floor:
            return None
    # Stability compares independent recomputations before/after the most recent evidence.
    previous = all_estimates(state.evidence[:-3])
    changes = [abs(skills[s].difficulty_estimate - previous[s].difficulty_estimate)
               for s in MAJORS if skills[s].difficulty_estimate is not None and previous[s].difficulty_estimate is not None]
    if overall_confidence(skills, state.evidence) >= .48 and changes and max(changes) < 1:
        return 'sufficient_evidence'
    return None


class AssessmentEngine:
    def __init__(self, repository: AssessmentRepository, bank: QuestionBank, evaluator: AnswerEvaluator, ttl: int):
        self.repository, self.bank, self.evaluator, self.ttl = repository, bank, evaluator, ttl
        self.busy: set[UUID] = set()

    def start(self, request: StartRequest) -> dict:
        now = time.time()
        state = AssessmentState(assessment_id=uuid4(), learner_id=uuid4(), self_report=request.self_report,
                                started_at=now, updated_at=now)
        state.current = select_question(state, self.bank)
        if not state.current:
            logger.error('Assessment question selection failed at start')
            raise TutorError('no_question', 'No placement questions are available. Please use ordinary chat.', 503)
        self.repository.create(state)
        logger.info('Assessment started: %s', state.assessment_id)
        return self.public(state)

    def load(self, assessment_id: UUID) -> AssessmentState:
        state = self.repository.get(assessment_id)
        if state.status == 'in_progress' and state.bank_version != BANK_VERSION:
            raise TutorError('assessment_bank_changed', 'The question bank changed. Start a new assessment; completed profiles remain available.', 409)
        if state.status == 'in_progress' and time.time() - state.updated_at > self.ttl:
            raise TutorError('assessment_expired', 'This placement assessment expired. Start a new one; completed profiles remain saved.', 410)
        return state

    def public(self, state: AssessmentState) -> dict:
        return {'assessment_id': str(state.assessment_id), 'learner_id': str(state.learner_id),
            'status': state.status, 'questions_answered': len(state.evidence),
            'question_number': len(state.evidence) + 1 if state.current else None,
            'maximum_questions': MAX_QUESTIONS,
            'question': state.current.public() if state.current else None,
            'result': state.profile.model_dump(mode='json') if state.profile else None}

    async def answer(self, assessment_id: UUID, request: AnswerRequest) -> dict:
        if assessment_id in self.busy:
            raise TutorError('assessment_busy', 'An answer is being processed. Please wait and retry.', 409)
        self.busy.add(assessment_id)
        try:
            state = self.load(assessment_id)
            for entry in state.evidence:
                if entry.submission_id == request.submission_id:
                    if (entry.question.id, entry.answer, entry.dont_know) != (request.question_id, request.answer, request.dont_know):
                        raise TutorError('submission_conflict', 'This submission ID was used for a different answer.', 409)
                    return {**self.public(state), 'accepted': True, 'replayed': True, 'notice': None}
            if state.status != 'in_progress':
                raise TutorError('assessment_complete', 'This assessment is already complete.', 409)
            if not state.current or state.current.id != request.question_id:
                raise TutorError('stale_question', 'This question is no longer current. Reload the assessment.', 409)
            evaluation = await self.evaluator.evaluate(state.current, request)
            expected_version = state.version
            state.evidence.append(Evidence(question=state.current, answer=request.answer,
                submission_id=request.submission_id, dont_know=request.dont_know, evaluation=evaluation))
            state.current = None
            reason = stopping_reason(state)
            if not reason:
                state.current = select_question(state, self.bank)
                if state.current is None:
                    logger.warning('Assessment question selection exhausted the bank')
                    reason = 'bank_exhausted'
            if reason:
                state.status = 'completed'
                state.completed_at = time.time()
                state.profile = build_profile(state, reason)
            state.version += 1
            state.updated_at = time.time()
            self.repository.save_answer(state, expected_version)
            if reason:
                logger.info('Assessment completed: %s (%s)', assessment_id, reason)
            notice = 'This response could not be evaluated. It did not count as incorrect; other questions will provide evidence.' if evaluation.method == 'unavailable' else None
            return {**self.public(state), 'accepted': True, 'replayed': False, 'notice': notice}
        finally:
            self.busy.discard(assessment_id)
