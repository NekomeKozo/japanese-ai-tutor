import json
from pathlib import Path
from app.jlpt.schemas import Question

BANK_VERSION = 'jlpt-v1'


def content_key(q):
    return (q.level, q.prompt.strip(), q.passage_text or '', tuple(sorted(q.choices)))


class Bank:
    def __init__(self, items, version=BANK_VERSION):
        self.items = tuple(items)
        self.version = version
        if len({q.id for q in items}) != len(items):
            raise ValueError('Duplicate JLPT question IDs')
        if len({content_key(q) for q in items}) != len(items):
            raise ValueError('Duplicate JLPT question content')
        passages = {}
        for q in items:
            if q.passage_id:
                if q.passage_id in passages and passages[q.passage_id] != q.passage_text:
                    raise ValueError('Inconsistent passage identity')
                passages[q.passage_id] = q.passage_text
        self.by_id = {q.id: q for q in items}

    @classmethod
    def load(cls):
        items = []
        for level in ('n5', 'n4'):
            data = json.loads((Path(__file__).with_name('data') / f'{level}.json').read_text(encoding='utf-8'))
            items.extend(Question.model_validate(q) for q in data)
        return cls(items)

    def catalog(self):
        return {'bank_version': self.version, 'levels': ['N5','N4'],
                'sections': ['mixed','vocabulary','kanji','grammar','reading'],
                'modes': ['quick','standard','focused','weakness','mock'], 'question_counts': [5,10,20],
                'coverage': {level: {section: sum(q.status == 'approved' and q.level == level and q.section == section for q in self.items)
                                    for section in ('vocabulary','kanji','grammar','reading')} for level in ('N5','N4')},
                'note': 'Original JLPT-style practice. Raw accuracy is not an official JLPT score or pass prediction.'}
