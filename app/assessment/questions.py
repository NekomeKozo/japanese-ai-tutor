import json
from pathlib import Path

from app.assessment.schemas import Question, SKILLS

BANK_VERSION = 'phase2-v1'


class QuestionBank:
    def __init__(self, items: list[Question]):
        if len({q.id for q in items}) != len(items):
            raise ValueError('Duplicate question IDs')
        self.items = items

    @classmethod
    def load(cls, path: Path | None = None):
        path = path or Path(__file__).with_name('data') / 'questions.json'
        items = [Question.model_validate(item) for item in json.loads(path.read_text(encoding='utf-8'))]
        if set(q.skill for q in items) != set(SKILLS):
            raise ValueError('Question bank must cover all assessment skills')
        return cls(items)

    def validated_candidates(self, raw: str) -> list[Question]:
        """Import boundary for future generated candidates; never auto-publish them.

        Schema-valid generated items still require linguistic/difficulty review before
        a developer includes them in the bank. Live generation is deliberately optional.
        """
        candidates = [Question.model_validate(item) for item in json.loads(raw)]
        existing = {q.id for q in self.items}
        if len({q.id for q in candidates}) != len(candidates) or any(q.id in existing for q in candidates):
            raise ValueError('Duplicate candidate IDs')
        return candidates
