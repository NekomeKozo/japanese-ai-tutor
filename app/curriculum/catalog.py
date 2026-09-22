"""Small prototype curriculum. Level labels are study references, not official lists."""
from dataclasses import dataclass


@dataclass(frozen=True)
class ContentTopic:
    key: str
    title: str
    skill: str
    difficulty: float
    prerequisites: tuple[str, ...] = ()
    goals: tuple[str, ...] = ()
    # A tiny reviewed recall template for non-generative topics.
    prompt: str = ''
    answer: str = ''
    distractors: tuple[str, ...] = ()
    note: str = ''

    @property
    def level(self):
        return 'beginner' if self.difficulty < 1 else 'N5' if self.difficulty < 4 else 'N4' if self.difficulty < 7 else 'N3' if self.difficulty < 10 else 'N2'

    @property
    def activity_type(self):
        return {'grammar': 'guided_practice', 'vocabulary': 'vocabulary_review', 'kanji': 'kanji_recognition',
                'reading': 'reading_comprehension', 'sentence_construction': 'sentence_construction',
                'hiragana': 'multiple_choice', 'katakana': 'multiple_choice'}[self.skill]


_topics = [
    ContentTopic('hiragana', 'Hiragana foundations', 'hiragana', 0, prompt='Which sound does あ represent?', answer='a', distractors=('i','u'), note='あ represents the vowel a.'),
    ContentTopic('katakana', 'Katakana foundations', 'katakana', 0, prompt='Which hiragana has the same sound as カ?', answer='か', distractors=('た','ま'), note='カ and か both represent ka.'),
]

# Existing Phase 3 keys are reused wherever the learning concept is the same.
for key, title, difficulty, prerequisites, goals in [
    ('copula_desu','です and simple statements',1,(),('travel','conversation')),
    ('particle_wa_vs_ga','Topic は and subject が',2,('copula_desu',),('conversation',)),
    ('particle_no','Possession with の',1,('copula_desu',),('travel',)),
    ('particle_wo','Objects with を',2,('verb_forms',),('conversation',)),
    ('particle_ni_destination','Destination particle に',2,('verb_forms',),('travel',)),
    ('particle_de_location','Location particle で',2,('verb_forms',),('travel',)),
    ('destination_location','Destination に and action location で',2,('particle_ni_destination','particle_de_location'),('travel',)),
    ('verb_forms','Basic dictionary and ます forms',1,(),('conversation','work')),
    ('verb_masu_stem','The ます stem',2,('verb_forms',),()),
    ('verb_negative','Negative verb forms',2,('verb_forms',),()),
    ('verb_past_tense','Past tense',2,('verb_forms',),('conversation',)),
    ('verb_te_form','て-form',4,('verb_past_tense',),()),
    ('adjective_i_conjugation','い-adjective forms',2,('copula_desu',),()),
    ('adjective_na_conjugation','な-adjective forms',2,('copula_desu',),()),
    ('tai_form','Expressing wishes with 〜たい',2,('verb_masu_stem',),('travel','conversation')),
    ('te_kudasai','Requests with 〜てください',4,('verb_te_form',),('travel','work')),
    ('te_iru','Ongoing actions with 〜ている',4,('verb_te_form',),('conversation',)),
    ('grammar_nagara','Doing two things with 〜ながら',5,('verb_masu_stem',),('conversation',)),
    ('ta_koto','Experiences with 〜たことがある',5,('verb_past_tense',),('conversation',)),
    ('grammar_comparison','Comparisons with より and ほう',4,('adjective_i_conjugation',),()),
    ('grammar_potential','Potential forms',5,('verb_forms','verb_te_form'),('work',)),
    ('grammar_conditional','Conditions with 〜たら',6,('verb_past_tense',),()),
    ('grammar_passive','Passive forms',7,('verb_forms','verb_te_form'),('work',)),
    ('grammar_youni','Goals and changes with ように',8,('grammar_potential',),('university','work')),
]:
    _topics.append(ContentTopic(key,title,'grammar',difficulty,prerequisites,goals))

for key,title,difficulty,goals,prompt,answer,distractors,note in [
    ('vocab_greetings','Greetings and courtesy',0,('travel','conversation'),'Which phrase means “thank you”?','ありがとう',('おはよう','さようなら'),'ありがとう means thank you.'),
    ('vocab_numbers','Numbers and prices',1,('travel',),'What does 三 mean?','three',('one','five'),'三（さん）means three.'),
    ('vocab_food','Food and ordering',1,('travel',),'What is 水（みず）?','water',('rice','tea'),'水 means water.'),
    ('vocab_transport','Transport and directions',2,('travel',),'What does 駅（えき）mean?','station',('school','shop'),'駅 means station.'),
    ('vocab_daily','Daily routines',2,('conversation',),'What does 起きる（おきる）mean?','to wake up',('to sleep','to walk'),'起きる can mean to wake up or get up.'),
    ('vocab_family','Family words',2,('conversation',),'What does 兄（あに）mean?','my older brother',('my younger sister','my mother'),'兄 refers to one’s own older brother.'),
    ('vocab_time','Time and appointments',2,('work','travel'),'What does 明日（あした）mean?','tomorrow',('yesterday','today'),'明日 means tomorrow.'),
    ('vocab_shopping','Shopping and sizes',2,('travel',),'What does 安い（やすい）mean?','inexpensive',('expensive','heavy'),'安い means inexpensive.'),
    ('vocab_health','Health and the body',4,('travel',),'What does 頭（あたま）mean?','head',('hand','foot'),'頭 means head.'),
    ('vocab_work','Work and tasks',5,('work',),'What does 会議（かいぎ）mean?','meeting',('holiday','salary'),'会議 means a meeting or conference.'),
    ('vocab_opinions','Opinions and discussion',7,('conversation','university'),'What does 意見（いけん）mean?','opinion',('promise','reason'),'意見 means an opinion or view.'),
    ('vocab_study','Study and research',8,('university',),'What does 調査（ちょうさ）mean?','investigation or survey',('graduation','entrance exam'),'調査 means investigation or survey.'),
]:
    _topics.append(ContentTopic(key,title,'vocabulary',difficulty,(),goals,prompt,answer,distractors,note))

for key,title,difficulty,kanji,answer,distractors in [
    ('kanji_numbers','Number kanji',1,'一','one',('two','ten')),
    ('kanji_days','Days and nature',1,'月','moon; month',('fire','water')),
    ('kanji_people','People and family',1,'人','person',('mountain','tree')),
    ('kanji_places','Places and directions',2,'山','mountain',('river','field')),
    ('kanji_gaku_meaning','学: meaning',2,'学','study; learning',('rest','go')),
    ('kanji_gaku_reading','学: reading in 学生',2,'学生','がくせい',('せんせい','がっこう')),
    ('kanji_transport','Transport kanji',4,'車','vehicle; car',('rain','flower')),
    ('kanji_actions','Common action kanji',4,'飲','drink',('read','write')),
    ('kanji_work','Work-related kanji',5,'社','company; shrine',('sea','voice')),
    ('kanji_ideas','Ideas and feelings',7,'意','idea; intention',('store','bird')),
]:
    question = f'Choose the reading of {kanji}.' if key.endswith('_reading') else f'Choose the meaning of {kanji}.'
    _topics.append(ContentTopic(key,title,'kanji',difficulty,(),('work',) if key=='kanji_work' else (),question,answer,distractors,f'{kanji}: {answer}.'))

for key,title,difficulty,prerequisites,prompt,answer,distractors in [
    ('reading_signs','Everyday signs',1,(),'入口（いりぐち） → What does the sign indicate?','entrance',('exit','toilet')),
    ('reading_n5','A short daily note',2,('verb_forms',),'今日は休みです。家で本を読みます。\nWhere will the writer read?','at home',('at school','at the station')),
    ('reading_n4','An appointment notice',5,('verb_past_tense',),'明日の会議は午後三時からです。資料を持ってきてください。\nWhat should attendees bring?','documents',('lunch','an umbrella')),
    ('reading_n3','A short argument',8,('grammar_conditional',),'電車で通えば、本を読む時間が増える。一方、車ほど自由には移動できない。\nWhich advantage of taking the train is given?','more time for reading',('cheaper tickets','freedom to go anywhere')),
]:
    _topics.append(ContentTopic(key,title,'reading',difficulty,prerequisites,('travel',) if key=='reading_signs' else (),prompt,answer,distractors,'Read for the stated detail; do not add information absent from the passage.'))

for key,title,difficulty,prerequisites in [
    ('sentence_intro','Introduce yourself',1,('copula_desu',)),
    ('sentence_routine','Describe your routine',2,('verb_forms','particle_wo')),
    ('sentence_experience','Describe a past experience',5,('ta_koto',)),
    ('sentence_opinion','Give an opinion and reason',7,('grammar_conditional',)),
]:
    _topics.append(ContentTopic(key,title,'sentence_construction',difficulty,prerequisites,('conversation','work')))

CATALOG = {topic.key: topic for topic in _topics}
# Bridge the broader Phase 2/3 evidence tags directly into reviewable activities.
# These are eligible only after exposure; new learners see specific catalog topics.
REVIEW_ONLY = {'vocabulary_meaning','kanji_reading','kanji_meaning','reading_meaning',
               'sentence_construction','sentence_patterns','adjective_forms'}
for topic in [
    ContentTopic('vocabulary_meaning','Vocabulary in context','vocabulary',2,prompt='朝ご飯を食べます。\nWhat does 朝ご飯（あさごはん）mean?',answer='breakfast',distractors=('dinner','lunch'),note='朝ご飯 means breakfast.'),
    ContentTopic('kanji_reading','Basic kanji readings','kanji',2,prompt='Choose the reading of 学校.',answer='がっこう',distractors=('がくせい','せんせい'),note='学校（がっこう）means school.'),
    ContentTopic('kanji_meaning','Basic kanji meanings','kanji',2,prompt='What does 川 mean?',answer='river',distractors=('mountain','forest'),note='川（かわ）means river.'),
    ContentTopic('reading_meaning','Reading for meaning','reading',2,prompt='田中さんは毎朝七時に起きます。\nWhen does Tanaka wake up?',answer='at seven every morning',distractors=('at eight every morning','at seven every evening'),note='毎朝 means every morning; 七時 means seven o’clock.'),
    ContentTopic('sentence_construction','Build clear Japanese sentences','sentence_construction',2,('verb_forms',)),
    ContentTopic('sentence_patterns','Core sentence patterns','grammar',2,('copula_desu',)),
    ContentTopic('adjective_forms','Adjective forms review','grammar',2,('copula_desu',)),
]:
    CATALOG[topic.key]=topic
CATALOG_VERSION = 'phase4-v1'


def validate_catalog(catalog=CATALOG):
    visiting, visited = set(), set()
    def visit(key):
        if key in visiting: raise ValueError('Curriculum prerequisite cycle')
        if key in visited: return
        if key not in catalog: raise ValueError('Missing curriculum prerequisite')
        visiting.add(key)
        topic = catalog[key]
        if not 0 <= topic.difficulty <= 14: raise ValueError('Invalid difficulty')
        if topic.prompt and (len(topic.distractors) < 2 or topic.answer in topic.distractors):
            raise ValueError('Invalid template answers')
        for prerequisite in topic.prerequisites: visit(prerequisite)
        visiting.remove(key); visited.add(key)
    for key in catalog: visit(key)


validate_catalog()
