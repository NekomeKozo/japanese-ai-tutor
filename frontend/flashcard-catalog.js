'use strict';

// Application-authored examples. Beginner is a practice label, not an official JLPT list.
// topic_id links exact existing items only; null identities can be mapped in a later phase.
function validateFlashcardCatalog(records) {
  if (!Array.isArray(records)) throw new TypeError('Flashcard catalog must be an array.');
  const ids = new Set();
  return Object.freeze(records.map(record => {
    if (!record || typeof record !== 'object' || typeof record.id !== 'string' || !/^[a-z][a-z0-9_]+$/.test(record.id) || ids.has(record.id)) throw new TypeError('Invalid or duplicate flashcard ID.');
    ids.add(record.id);
    if (!['vocabulary','kanji','grammar'].includes(record.category)) throw new TypeError('Invalid flashcard category.');
    for (const key of ['level','front','back','meaning']) if (typeof record[key] !== 'string' || !record[key].trim()) throw new TypeError(`Missing flashcard ${key}.`);
    for (const key of ['reading','explanation','example_japanese','example_translation']) if (record[key] != null && (typeof record[key] !== 'string' || !record[key].trim())) throw new TypeError(`Invalid flashcard ${key}.`);
    if (Boolean(record.example_japanese) !== Boolean(record.example_translation)) throw new TypeError('Example needs both Japanese and translation.');
    if (record.category === 'vocabulary' && !record.reading) throw new TypeError('Vocabulary needs a kana reading.');
    if (record.topic_id != null && (typeof record.topic_id !== 'string' || !/^[a-z][a-z0-9_]+$/.test(record.topic_id))) throw new TypeError('Invalid topic link.');
    if (!Array.isArray(record.tags) || record.tags.some(tag => typeof tag !== 'string' || !tag.trim())) throw new TypeError('Invalid flashcard tags.');
    return Object.freeze({...record, tags:Object.freeze([...record.tags])});
  }));
}

const flashcardCatalog = validateFlashcardCatalog([
  ...[
    ['neko','猫','ねこ','cat','猫がいます。','There is a cat.',null],
    ['gakkou','学校','がっこう','school','学校に行きます。','I go to school.','vocab_gakkou'],
    ['yakusoku','約束','やくそく','promise; appointment','友達と約束があります。','I have an appointment with a friend.',null],
    ['mizu','水','みず','water','水を飲みます。','I drink water.','vocab_mizu'],
    ['eki','駅','えき','station','駅は近いです。','The station is nearby.','vocab_eki'],
    ['taberu','食べる','たべる','to eat','朝ご飯を食べます。','I eat breakfast.','vocab_taberu'],
    ['iku','行く','いく','to go','日本に行きます。','I go to Japan.','vocab_iku'],
    ['toshokan','図書館','としょかん','library','図書館で本を読みます。','I read books at the library.','vocab_toshokan'],
    ['kyou','今日','きょう','today','今日は休みです。','Today is a day off.','vocab_kyou'],
    ['ashita','明日','あした','tomorrow','明日、勉強します。','I will study tomorrow.','vocab_ashita'],
    ['yasui','安い','やすい','inexpensive','この本は安いです。','This book is inexpensive.','vocab_yasui'],
    ['arigatou','ありがとう','ありがとう','thank you','ありがとう。助かりました。','Thank you. That helped.','vocab_arigatou']
  ].map(([id,front,reading,meaning,example_japanese,example_translation,topic_id]) => ({id:`fc_vocab_${id}`,category:'vocabulary',level:'Beginner',front,back:meaning,reading,meaning,explanation:'Recall the word, then read it in the example sentence.',example_japanese,example_translation,topic_id,tags:['everyday']})),
  ...[
    ['ichi','一','いち / ひと','one','一つ','ひとつ','one thing','kanji_ichi'],
    ['tsuki','月','げつ / がつ / つき','moon; month','月曜日','げつようび','Monday','kanji_tsuki'],
    ['hito','人','じん / にん / ひと','person','日本人','にほんじん','Japanese person','kanji_hito'],
    ['yama','山','さん / やま','mountain','山','やま','mountain','kanji_yama'],
    ['gaku','学','がく / まなぶ','study; learning','学校','がっこう','school','kanji_gaku'],
    ['kuruma','車','しゃ / くるま','car; vehicle','電車','でんしゃ','train','kanji_kuruma'],
    ['nomu','飲','いん / のむ','drink','飲む','のむ','to drink','kanji_nomu'],
    ['sha','社','しゃ / やしろ','company; shrine','会社','かいしゃ','company','kanji_sha'],
    ['sei','生','せい / しょう / いきる','life; birth','学生','がくせい','student','kanji_sei'],
    ['kou','校','こう','school','学校','がっこう','school','kanji_kou']
  ].map(([id,front,reading,meaning,word,kana,translation,topic_id]) => ({id:`fc_kanji_${id}`,category:'kanji',level:'Beginner',front,back:meaning,reading,meaning,explanation:`Selected readings, not an exhaustive list. Readings depend on the word. Example: ${word}（${kana}）— ${translation}.`,example_japanese:word,example_translation:translation,topic_id,tags:['character','reading-in-context']})),
  ...[
    ['tai','〜たい','want to do something','Attach たい to the verb stem before ます. It conjugates like an い-adjective.','日本に行きたいです。','I want to go to Japan.','tai_form'],
    ['ni','に · destination','destination of movement','Use に after a destination with a movement verb such as 行く.','学校に行きます。','I go to school.','particle_ni_destination'],
    ['de','で · action location','where an action happens','Use で after the place where an action is performed.','図書館で勉強します。','I study at the library.','particle_de_location'],
    ['wa','は · topic','introduce the topic','は marks what the sentence is about. As a particle, it is pronounced わ.','私は学生です。','I am a student.','particle_wa_vs_ga'],
    ['past','〜ました','polite past of a verb','Replace ます with ました for a polite affirmative past statement.','昨日、本を読みました。','I read a book yesterday.','verb_past_tense'],
    ['te','〜てください','a polite request to do something','Add ください to a verb in its て-form. The て-form depends on the verb group.','ここに名前を書いてください。','Please write your name here.','verb_te_form'],
    ['i','〜くないです','negative of an い-adjective','Replace the final い with くないです. いい is irregular: よくないです.','この本は高くないです。','This book is not expensive.','adjective_i_conjugation'],
    ['na','〜な + noun','a な-adjective describing a noun','Use な between a な-adjective and the noun it describes.','静かな部屋で勉強します。','I study in a quiet room.','adjective_na_conjugation']
  ].map(([id,front,meaning,explanation,example_japanese,example_translation,topic_id]) => ({id:`fc_grammar_${id}`,category:'grammar',level:'Beginner',front,back:meaning,meaning,explanation,example_japanese,example_translation,topic_id,tags:['pattern']}))
]);
