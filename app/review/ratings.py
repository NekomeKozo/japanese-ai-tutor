from app.review.policy import POLICY

def rating(evidence, mastery, policy=POLICY):
    score = evidence.score
    if score < policy.again_below:
        return 'again'
    if score < policy.good_at or evidence.hint_used or evidence.answer_revealed:
        return 'hard'
    independent = evidence.hint_used is False and evidence.quality >= .7
    appropriate = evidence.learner_level is not None and evidence.difficulty >= evidence.learner_level - 1
    if (score >= policy.easy_at and independent and appropriate and evidence.evidence_type in ('production','recall','application')
            and mastery.get('confidence',0) >= policy.easy_confidence and (mastery.get('score') or 0) >= .68):
        return 'easy'
    return 'good'
