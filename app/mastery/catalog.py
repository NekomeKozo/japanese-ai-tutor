"""Reviewed item identities. A category or compound never implies component mastery."""

# Curriculum topic -> exact item actually tested by its fixed template.
VOCAB_ITEMS = {
    'vocab_greetings': ('vocab_arigatou', 'ありがとう', 'ありがとう', 'thank you'),
    'vocab_numbers': ('vocab_san', '三', 'さん', 'three'),
    'vocab_food': ('vocab_mizu', '水', 'みず', 'water'),
    'vocab_transport': ('vocab_eki', '駅', 'えき', 'station'),
    'vocab_daily': ('vocab_okiru', '起きる', 'おきる', 'to wake up'),
    'vocab_family': ('vocab_ani', '兄', 'あに', 'my older brother'),
    'vocab_time': ('vocab_ashita', '明日', 'あした', 'tomorrow'),
    'vocab_shopping': ('vocab_yasui', '安い', 'やすい', 'inexpensive'),
    'vocab_health': ('vocab_atama', '頭', 'あたま', 'head'),
    'vocab_work': ('vocab_kaigi', '会議', 'かいぎ', 'meeting'),
    'vocab_opinions': ('vocab_iken', '意見', 'いけん', 'opinion'),
    'vocab_study': ('vocab_chousa', '調査', 'ちょうさ', 'investigation or survey'),
}
KANJI_ITEMS = {
    'kanji_numbers': ('kanji_ichi', '一'), 'kanji_days': ('kanji_tsuki', '月'),
    'kanji_people': ('kanji_hito', '人'), 'kanji_places': ('kanji_yama', '山'),
    'kanji_gaku_meaning': ('kanji_gaku', '学'), 'kanji_gaku_reading': ('kanji_gaku', '学'),
    'kanji_transport': ('kanji_kuruma', '車'), 'kanji_actions': ('kanji_nomu', '飲'),
    'kanji_work': ('kanji_sha', '社'), 'kanji_ideas': ('kanji_i', '意'),
}


def canonical(key, *, fixed=False):
    # Broad category evidence is mapped to an item only for a known fixed exercise.
    if key in ('kanji_gaku_meaning', 'kanji_gaku_reading'):
        return 'kanji_gaku'
    if fixed and key in VOCAB_ITEMS:
        return VOCAB_ITEMS[key][0]
    if fixed and key in KANJI_ITEMS:
        return KANJI_ITEMS[key][0]
    return key


def topic_type(key):
    from app.learner.catalog import TOPICS
    topic = TOPICS.get(key)
    if not topic or key.startswith('other_'):
        return None
    if topic.kind == 'grammar':
        return 'grammar'
    if topic.kind == 'vocabulary' and topic.reading and topic.meaning:
        return 'vocabulary'
    if topic.kind == 'kanji' and len(topic.label) == 1:
        return 'kanji'
    return None


def curriculum_key(key):
    return canonical(key, fixed=True)
