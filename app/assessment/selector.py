import random

from app.assessment.questions import QuestionBank
from app.assessment.schemas import AssessmentState, GRAMMAR_PARTS, MAJORS, SCRIPTS, SKILLS
from app.assessment.scoring import all_estimates, evidence_for


def present(question, state):
    # Stable within an assessment, different across learners; never bias correct answers
    # toward the same screen position. Do not mutate the shared bank.
    question = question.model_copy(deep=True)
    random.Random(f'{state.assessment_id}:{question.id}').shuffle(question.choices)
    return question


def select_question(state: AssessmentState, bank: QuestionBank):
    asked = {e.question.id for e in state.evidence}
    remaining = [q for q in bank.items if q.id not in asked]
    if not remaining:
        return None
    counts = {s: sum(e.question.skill == s for e in state.evidence) for s in SKILLS}
    estimates = all_estimates(state.evidence)
    # Four-item script screen before introducing grammar-heavy items.
    for skill in SCRIPTS:
        if counts[skill] < 2:
            candidates = [q for q in remaining if q.skill == skill]
            if candidates:
                return present(min(candidates, key=lambda q: (q.difficulty, q.id)), state)
    # Sample each specific skill at least once, then spend questions on major gaps.
    unseen = [s for s in SKILLS if not counts[s] and any(q.skill == s for q in remaining)]
    if unseen:
        skill = unseen[0]
    else:
        candidates = [s for s in MAJORS if any(q.skill == s or (s == 'grammar' and q.skill in GRAMMAR_PARTS) for q in remaining)
                      and not (s in SCRIPTS and counts[s] >= 2)]
        if not candidates:
            return None
        skill = min(candidates, key=lambda s: (estimates[s].evidence_count >= 2,
                    estimates[s].evidence_count >= 3, estimates[s].confidence, MAJORS.index(s)))
    candidates = [q for q in remaining if q.skill == skill or
                  (skill == 'grammar' and q.skill in GRAMMAR_PARTS)]
    own = [e for e in evidence_for(skill, state.evidence) if e.evaluation.score is not None]
    if own:
        last = own[-1]
        # A first correct answer moves only one bank band; repeated success accelerates.
        step = 3 if len(own) >= 2 and all(e.evaluation.score >= .85 for e in own[-2:]) else 2
        if last.evaluation.score >= .85:
            target = min(14, last.question.difficulty + step)
        elif last.evaluation.score < .6:
            target = max(0, last.question.difficulty - 2)
        else:
            target = last.question.difficulty
        # Once a boundary has been crossed, test around the posterior instead of oscillating.
        if any(e.evaluation.score >= .65 for e in own) and any(e.evaluation.score < .65 for e in own):
            target = estimates[skill].difficulty_estimate or 0
    else:
        answered = [e for e in state.evidence if e.question.skill not in SCRIPTS and e.evaluation.score is not None]
        target = {'beginner': 0, 'N4': 3}.get(state.self_report, 2)
        # Screening evidence transfers only to item selection, never to other skill scores.
        successes = [e for e in answered if e.evaluation.score >= .85]
        if len(successes) >= 2:
            target = min(11, max(e.question.difficulty for e in successes[-3:]) + 2)
        if answered and sum(e.evaluation.score for e in answered[-3:]) / len(answered[-3:]) < .35:
            target = max(0, max((e.question.difficulty for e in successes[-3:]), default=0) - 2)
    return present(min(candidates, key=lambda q: (abs(q.difficulty - target), q.difficulty, q.id)), state)
