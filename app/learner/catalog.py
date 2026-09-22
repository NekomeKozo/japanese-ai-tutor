"""Small reviewed vocabulary for observations, not a generated content database."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Topic:
    key: str
    label: str
    skill: str
    kind: str
    difficulty: float = 2
    reading: str | None = None
    meaning: str | None = None


TOPICS = {t.key: t for t in [
    Topic('particle_ni_destination', 'Destination particle に', 'grammar', 'grammar'),
    Topic('particle_de_location', 'Location particle で', 'grammar', 'grammar'),
    Topic('particle_wa_vs_ga', 'は vs が', 'grammar', 'grammar'),
    Topic('destination_location', 'Destination and location particles', 'grammar', 'grammar'),
    Topic('verb_past_tense', 'Past tense', 'grammar', 'grammar'),
    Topic('verb_te_form', 'て-form', 'grammar', 'grammar', 4),
    Topic('verb_forms', 'Verb forms', 'grammar', 'grammar'),
    Topic('adjective_i_conjugation', 'い-adjective forms', 'grammar', 'grammar'),
    Topic('adjective_na_conjugation', 'な-adjective forms', 'grammar', 'grammar'),
    Topic('adjective_forms', 'Adjective forms', 'grammar', 'grammar'),
    Topic('tai_form', '〜たい', 'grammar', 'grammar'),
    Topic('sentence_patterns', 'Sentence patterns', 'grammar', 'grammar'),
    Topic('word_order', 'Japanese word order', 'sentence_construction', 'grammar'),
    Topic('politeness_mismatch', 'Context-appropriate politeness', 'grammar', 'grammar'),
    Topic('vocabulary_meaning', 'Vocabulary meaning', 'vocabulary', 'vocabulary'),
    Topic('vocab_taberu', '食べる', 'vocabulary', 'vocabulary', 2, 'たべる', 'to eat'),
    Topic('vocab_iku', '行く', 'vocabulary', 'vocabulary', 2, 'いく', 'to go'),
    Topic('vocab_ramen', 'ラーメン', 'vocabulary', 'vocabulary', 1, 'らーめん', 'ramen'),
    Topic('kanji_reading', 'Kanji readings', 'kanji', 'kanji'),
    Topic('kanji_meaning', 'Kanji meanings', 'kanji', 'kanji'),
    Topic('kanji_gaku_reading', '学 · reading', 'kanji', 'kanji', 2, 'がく / まなぶ', 'study; learning'),
    Topic('kanji_gaku_meaning', '学 · meaning', 'kanji', 'kanji', 2, None, 'study; learning'),
    Topic('hiragana', 'Hiragana recognition', 'hiragana', 'script', 0),
    Topic('katakana', 'Katakana recognition', 'katakana', 'script', 0),
    Topic('reading_meaning', 'Reading for meaning', 'reading', 'reading'),
    Topic('sentence_construction', 'Sentence construction', 'sentence_construction', 'writing'),
]}
for skill in ('hiragana', 'katakana', 'vocabulary', 'grammar', 'particles', 'verb_conjugation',
              'adjective_conjugation', 'kanji', 'reading', 'sentence_construction'):
    TOPICS[f'other_{skill}'] = Topic(f'other_{skill}', f'Other {skill.replace("_", " ")}', skill, 'general')

# Curriculum uses the same topic namespace and memory tables, not a second progress model.
CHAT_TOPIC_KEYS = tuple(TOPICS)
from app.curriculum.catalog import CATALOG
for item in CATALOG.values():
    TOPICS.setdefault(item.key, Topic(item.key,item.title,item.skill,
        'grammar' if item.skill=='grammar' else item.skill,item.difficulty))

ALIASES = {
    'particle_ni': 'particle_ni_destination', 'destination_particle': 'particle_ni_destination',
    'destination_particle_ni': 'particle_ni_destination', 'grammar_particle_ni': 'particle_ni_destination',
    'particle_de': 'particle_de_location', 'particle_wa_ga': 'particle_wa_vs_ga',
    'verb_past': 'verb_past_tense', 'past_tense': 'verb_past_tense', 'te_form': 'verb_te_form',
    'verb_tai': 'tai_form', '〜たい': 'tai_form', '食べる': 'vocab_taberu', 'verb_taberu': 'vocab_taberu',
    '行く': 'vocab_iku', 'verb_iku': 'vocab_iku', 'ラーメン': 'vocab_ramen',
    'vocabulary in context': 'vocabulary_meaning', 'sentence patterns': 'sentence_patterns',
    'destination and location particles': 'destination_location', 'topic marking': 'particle_wa_vs_ga',
    'verb forms': 'verb_forms', 'adjective forms': 'adjective_forms', 'kanji readings': 'kanji_reading',
    'kanji meanings': 'kanji_meaning', 'reading for meaning': 'reading_meaning',
    'translation meaning': 'reading_meaning', 'sentence construction': 'sentence_construction',
}


def normalize_topic(value: str, skill: str) -> tuple[str, bool]:
    value = value.strip().casefold()
    value = ALIASES.get(value, value)
    if value in TOPICS:
        return value, not value.startswith('other_')
    return f'other_{skill}', False


# Reviewed item identities for mastery; existing group IDs and observations are retained.
from app.mastery.catalog import VOCAB_ITEMS, KANJI_ITEMS
for _, (key, label, reading, meaning) in VOCAB_ITEMS.items():
    TOPICS.setdefault(key, Topic(key, label, 'vocabulary', 'vocabulary', 2, reading, meaning))
for key, label, reading, meaning in [
    ('vocab_toshokan', '図書館', 'としょかん', 'library'),
    ('vocab_kyou', '今日', 'きょう', 'today'), ('vocab_gakkou', '学校', 'がっこう', 'school')]:
    TOPICS.setdefault(key, Topic(key, label, 'vocabulary', 'vocabulary', 2, reading, meaning))
for key, label in list(KANJI_ITEMS.values()) + [('kanji_sei', '生'), ('kanji_kou', '校')]:
    TOPICS.setdefault(key, Topic(key, label, 'kanji', 'kanji', 2))
