from app.assessment.evaluator import normalize
from app.errors import TutorError


def evaluate(question, answer):
    answer = normalize(answer)
    if not answer:
        raise TutorError('jlpt_answer', 'Enter an answer.', 422)
    if question.choices and answer not in {normalize(c) for c in question.choices}:
        raise TutorError('jlpt_answer', 'Choose one of the displayed answers.', 422)
    return int(answer in {normalize(a) for a in question.answers})


def results(questions, attempts):
    sections = {}
    for q in questions:
        group = sections.setdefault(q.section, {'correct': 0, 'total': 0})
        group['total'] += 1
        group['correct'] += attempts.get(q.id, {}).get('correct', 0)
    correct = sum(s['correct'] for s in sections.values())
    for s in sections.values():
        s['accuracy'] = round(100*s['correct']/s['total'], 1)
    return {'correct': correct, 'total': len(questions), 'answered': len(attempts),
            'accuracy': round(100*correct/len(questions), 1) if questions else 0,
            'sections': sections, 'note': 'Practice accuracy only; not an official JLPT score or pass/fail result.'}
