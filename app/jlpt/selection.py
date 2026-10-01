import hashlib
from app.errors import TutorError


def select(bank, request, recent, weaknesses):
    count = request.question_count or (5 if request.mode == 'quick' else 20 if request.mode == 'mock' else 10)
    pool = [q for q in bank.items if q.status == 'approved' and q.level == request.level
            and (request.section == 'mixed' or q.section == request.section)]
    if len(pool) < count:
        raise TutorError('jlpt_bank_size', 'There are not enough approved questions for that selection. Choose fewer questions or mixed sections.', 422)
    def rank(q):
        return (q.id in recent, -(weaknesses.get(q.topic_id, 0) if request.mode == 'weakness' else 0),
                hashlib.sha256(f'{request.request_id}:{q.id}'.encode()).hexdigest())
    pool.sort(key=rank)
    if request.section != 'mixed' or (request.mode == 'weakness' and any(q.topic_id in weaknesses for q in pool)):
        selected = pool[:count]
    else:
        groups = [[q for q in pool if q.section == s] for s in ('vocabulary','kanji','grammar','reading')]
        selected = []
        while len(selected) < count:
            for group in groups:
                if group and len(selected) < count:
                    selected.append(group.pop(0))
    if request.mode == 'mock':
        selected.sort(key=lambda q: ('vocabulary','kanji','grammar','reading').index(q.section))
    return selected
