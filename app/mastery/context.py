"""Derive evidence metadata from server-owned tasks, never from generated mastery claims."""
import hashlib
from app.mastery.catalog import canonical, topic_type


def task_context(topic, skill, prompt, question_type, evaluation, *, fixed=False, level=None, focus=None):
    kind = topic_type(canonical(topic, fixed=fixed))
    choice = evaluation == 'choice'
    dimension = focus
    if not dimension:
        if kind == 'vocabulary':
            dimension = 'production' if question_type in ('english_to_japanese', 'sentence_construction') else 'reading' if question_type == 'kanji_reading' else 'meaning'
        elif kind == 'grammar':
            dimension = ('production' if question_type in ('sentence_construction', 'english_to_japanese')
                         else 'application' if question_type == 'sentence_completion' else 'recognition' if choice else 'understanding')
        elif kind == 'kanji':
            dimension = 'on_reading' if topic == 'kanji_gaku_reading' else 'meaning' if fixed or question_type == 'kanji_meaning' else 'recognition'
    evidence_type = 'recognition' if choice else 'production' if dimension == 'production' else 'application' if dimension == 'application' else 'recall'
    return {'dimension': dimension, 'evidence_type': evidence_type, 'activity_type': question_type,
        'context_id': hashlib.sha256(prompt.strip().encode()).hexdigest(), 'hint_used': None,
        'learner_level': level, 'reading_context': '学生' if topic == 'kanji_gaku_reading' else None}
