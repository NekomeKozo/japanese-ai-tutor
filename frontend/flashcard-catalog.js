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

let flashcardCatalog = null;
let flashcardCatalogRequest = null;
async function loadFlashcardCatalog() {
  if (flashcardCatalog) return flashcardCatalog;
  if (!flashcardCatalogRequest) flashcardCatalogRequest = (async () => {
    const version = document.documentElement?.dataset?.assetVersion;
    const response = await fetch('/static/flashcard-catalog.json' + (version ? '?v=' + encodeURIComponent(version) : ''));
    if (!response.ok) throw new Error('The practice decks could not load. Try again.');
    flashcardCatalog = validateFlashcardCatalog(await response.json());
    return flashcardCatalog;
  })().finally(() => { flashcardCatalogRequest = null; });
  return flashcardCatalogRequest;
}
