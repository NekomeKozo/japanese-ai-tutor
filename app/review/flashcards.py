"""Public, authored card adapters; no scheduling decisions or private sources."""
import json
from functools import lru_cache
from pathlib import Path
from app.learner.catalog import TOPICS
from app.review.content import lesson, supported


@lru_cache(maxsize=1)
def catalog():
    records = json.loads((Path(__file__).resolve().parents[2] / 'frontend/flashcard-catalog.json').read_text(encoding='utf-8'))
    return {c['topic_id']: c for c in records if c.get('topic_id')}


def eligible(topic, dimension):
    if not supported(topic, dimension):
        return False
    if TOPICS[topic].kind != 'grammar':
        return True
    # Broader concepts must not be reviewed by a narrower example alone.
    return topic in ('tai_form', 'particle_ni_destination', 'particle_de_location') and dimension in ('recognition', 'understanding')


def card(topic, dimension):
    if not eligible(topic, dimension):
        return None
    item = TOPICS[topic]
    authored = catalog().get(topic, {})
    if item.kind == 'grammar':
        return dict(authored, front=f"Explain the use of {authored['front']}.", audio_text=authored['example_japanese'])
    task = lesson(dict(topic_id=topic, focus_dimension=dimension, difficulty=item.difficulty))
    return dict(id=topic, category=item.kind, level='Scheduled review', front=task.prompt,
        back=' / '.join(task.answers), meaning=item.meaning or task.answers[0],
        reading=item.reading if item.kind == 'vocabulary' else None,
        explanation=task.feedback, example_japanese=authored.get('example_japanese'),
        example_translation=authored.get('example_translation'),
        audio_text=task.reading_context or item.label)
