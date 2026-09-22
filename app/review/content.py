"""Authored retrieval tasks. Timing decisions do not live here."""
from app.learner.catalog import TOPICS
from app.curriculum.schemas import Lesson

# Character meaning, on-reading context/answer, kun-reading context/answer.
KANJI = {
 'kanji_ichi':('one',('一月','いちがつ'),('一つ','ひとつ')),
 'kanji_tsuki':('moon or month',('月曜日','げつようび'),('月','つき')),
 'kanji_hito':('person',('日本人','にほんじん'),('人','ひと')),
 'kanji_yama':('mountain',('富士山','ふじさん'),('山','やま')),
 'kanji_gaku':('study or learning',('学生','がくせい'),('学ぶ','まなぶ')),
 'kanji_kuruma':('car or vehicle',('電車','でんしゃ'),('車','くるま')),
 'kanji_nomu':('drink',('飲食','いんしょく'),('飲む','のむ')),
 'kanji_sha':('company or shrine',('会社','かいしゃ'),('社','やしろ')),
 'kanji_i':('meaning or intention',('意味','いみ'),None),
 'kanji_sei':('life or birth',('学生','がくせい'),('生きる','いきる')),
 'kanji_kou':('school',('学校','がっこう'),None),
}

def supported(topic,dimension):
    t=TOPICS.get(topic)
    if not t: return False
    if t.kind=='grammar': return dimension in ('recognition','understanding','application','production')
    if t.kind=='vocabulary': return bool(t.meaning and t.reading) and dimension in ('recognition','meaning','reading','production')
    if topic not in KANJI: return False
    return dimension in ('recognition','meaning','on_reading') or dimension=='kun_reading' and KANJI[topic][2] is not None

def title(topic,dimension):
    item=TOPICS[topic]
    return 'Recall: '+item.meaning if item.kind=='vocabulary' and dimension=='production' else item.label

def lesson(activity):
    topic=TOPICS[activity['topic_id']]; dim=activity['focus_dimension']
    if topic.kind=='grammar': return None  # Existing provider generates grammar exercises.
    variant=activity.get('review_variant',0)%2
    choices=[]; evaluation='fixed'; reading_context=None
    if topic.kind=='vocabulary':
        if dim=='reading':
            prompt=(f'Write the kana reading of {topic.label}.' if not variant else f'How is {topic.label} pronounced? Answer in kana.')
            answers=[topic.reading]
        elif dim=='production':
            prompt=(f'Write the Japanese word meaning: {topic.meaning}.' if not variant else f'Recall a Japanese word for “{topic.meaning}”. Kanji or kana is accepted.')
            answers=list(dict.fromkeys([topic.label,topic.reading]))
        else:
            prompt=f'What does {topic.label} mean?' if not variant else f'Recall the meaning of this word: {topic.label}.'
            answers=[topic.meaning]; evaluation='semantic'
            if dim=='recognition':
                alternatives=[t.meaning for t in TOPICS.values() if t.kind=='vocabulary' and t.meaning and t.meaning!=topic.meaning]
                choices=list(dict.fromkeys([topic.meaning]+alternatives))[:4]; evaluation='choice'
        feedback=f'{topic.label}（{topic.reading}）: {topic.meaning}.'
    else:
        meaning,on,kun=KANJI[topic.key]
        if dim in ('on_reading','kun_reading'):
            reading_context,answer=on if dim=='on_reading' else kun
            prompt=f'Write the kana reading of {reading_context}.' if not variant else f'Read {reading_context} in kana. This tests {topic.label} in this word.'
            answers=[answer]; feedback=f'{reading_context} is read {answer}.'
        else:
            prompt=f'What does {topic.label} mean?'; answers=[meaning]; evaluation='semantic'
            if dim=='recognition':
                choices=[meaning]+[v[0] for k,v in KANJI.items() if k!=topic.key][:3]; evaluation='choice'
            feedback=f'{topic.label}: {meaning}.'
    if choices:
        offset=activity.get('review_variant',0)%len(choices); choices=choices[offset:]+choices[:offset]
    guidance='Try recalling this from memory. You can skip if you prefer to return to it later.'
    if activity.get('reteach'):
        guidance=('Try a different approach: say the word aloud, connect it to a familiar situation, '
                  'then write your answer. For readings, separate the word into sounds. '
                  'After checking the feedback, write a new example instead of repeating the same answer.')
    return Lesson(topic_id=topic.key,difficulty=activity['difficulty'],title=title(topic.key,dim),
        explanation=guidance,examples=[],
        prompt=prompt,choices=choices,answers=answers,evaluation=evaluation,feedback=feedback,reading_context=reading_context)
