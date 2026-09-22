import json
from datetime import datetime, timedelta, timezone

from app.learner.catalog import TOPICS, CHAT_TOPIC_KEYS

MAX_CONTEXT_BYTES = 4000


def build_context(profile):
    cutoff = (datetime.now(timezone.utc) - timedelta(days=30)).isoformat()
    context = {
        'estimated_level': profile['estimated_level'],
        'profile_source': profile['profile_source'],
        'skills': {key: value['estimated_level'] for key, value in profile['skills'].items()
                   if key in ('hiragana', 'katakana', 'vocabulary', 'grammar', 'kanji', 'reading', 'sentence_construction')},
        'placement_starting_point': (profile['initial_placement'] or {}).get('recommended_starting_point', 'Start with introductory Japanese.')[:400],
        'preferences': profile['preferences'],
        'weak_topics': [topic['display_name'] for topic in profile['weak_topics'][:5]],
        'repeated_mistakes': [m['display_name'] for m in profile['common_mistakes']
                             if m['status'] == 'active' and m['last_seen_at'] >= cutoff][:5],
        'strong_topics': [topic['display_name'] for topic in profile['strong_topics'][:3]],
        'recent_topics': [topic['display_name'] for topic in profile['recent_topics'][:5]],
    }
    # Fixed taxonomy/preferences and truncation of lower-priority lists keep a hard byte budget.
    encoded = json.dumps(context, ensure_ascii=False, separators=(',', ':'))
    for field in ('recent_topics', 'strong_topics', 'repeated_mistakes', 'weak_topics'):
        while len(encoded.encode('utf-8')) > MAX_CONTEXT_BYTES and context[field]:
            context[field].pop()
            encoded = json.dumps(context, ensure_ascii=False, separators=(',', ':'))
    if len(encoded.encode('utf-8')) > MAX_CONTEXT_BYTES:
        # Defensive bound for incompatible/corrupt future profile data; never truncate JSON.
        context = {'estimated_level': str(profile['estimated_level'])[:80], 'preferences': profile['preferences']}
        encoded = json.dumps(context, ensure_ascii=False, separators=(',', ':'))
    return encoded


def observation_instructions():
    catalog = ', '.join(f'{key} ({TOPICS[key].label})' for key in CHAT_TOPIC_KEYS if not key.startswith('other_'))
    return ('\nReturn learning_observations for this turn only (maximum 8, one per topic). '
        'Use performance only when the learner actually attempts an answer or uses Japanese; never infer success '
        'from merely requesting or reading an explanation. For explanations use concept_explained with null score; '
        'for explicit help use requested_help with null score. For performance use score 0..1, and known error_tags '
        'only for mistakes. difficulty is optional evidence, never authority to change a profile. '
        'Do not invent exposure to words or kanji not studied in this turn. Unknown or uncertain observations should '
        'be omitted. Never assign a new overall learner level or overwrite profile/preferences. '
        'Allowed topic/error identifiers: ' + catalog + '.')


def preference_instructions(profile):
    prefs = profile['preferences']
    return (f'\nExplain in {prefs["explanation_language"]}; use a {prefs["correction_style"]} correction style. '
        + ('Offer kana readings for unfamiliar kanji. ' if prefs['furigana_enabled'] else 'Avoid adding readings unless asked. ')
        + 'Profile information should inform teaching, not force every lesson onto a weak topic. '
        'Respect the learner’s current question and never imply official JLPT certification.')
