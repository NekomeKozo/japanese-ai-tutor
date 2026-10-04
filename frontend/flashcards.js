'use strict';

// Transient practice only: no storage, requests, ratings or mastery events.
function createFlashcardSession(catalog, random = Math.random) {
  let cards = [], index = 0, revealed = false, finished = false, direction = 'ja-en';
  const snapshot = () => ({cards:[...cards], card:cards[index] || null, index, revealed, finished, direction});
  function shuffle() {
    for (let i = cards.length - 1; i > 0; i--) { const j = Math.floor(random() * (i + 1)); [cards[i],cards[j]] = [cards[j],cards[i]]; }
    index = 0; revealed = false; finished = false;
  }
  return {
    snapshot,
    start(category, selected = 'ja-en') {
      cards = catalog.filter(card => card.category === category);
      direction = category === 'vocabulary' && selected === 'en-ja' ? 'en-ja' : 'ja-en';
      index = 0; revealed = false; finished = false; return snapshot();
    },
    reveal() { if (cards.length && !finished) revealed = true; return snapshot(); },
    move(offset) { if (!finished && cards.length) { index = Math.max(0, Math.min(cards.length - 1, index + offset)); revealed = false; } return snapshot(); },
    restart(mix = false) { index = 0; revealed = false; finished = false; if (mix) shuffle(); return snapshot(); },
    finish() { finished = Boolean(cards.length); revealed = false; return snapshot(); },
    clear() { cards = []; index = 0; revealed = false; finished = false; return snapshot(); }
  };
}

const flashcards = createFlashcardSession(flashcardCatalog);
let flashcardPlayer = null;
function cleanFlashcardAudio() { flashcardPlayer?.destroy(); flashcardPlayer = null; }
function flashcardDirections() {
  const vocabulary = $('flashcard-deck').value === 'vocabulary';
  $('flashcard-direction').disabled = !vocabulary;
  if (!vocabulary) $('flashcard-direction').value = 'ja-en';
  $('flashcard-deck-note').textContent = vocabulary ? '12 everyday words · both directions.' : $('flashcard-deck').value === 'kanji' ? '10 characters · meanings and readings in context.' : '8 patterns · meanings, explanations and examples.';
}
function renderFlashcard() {
  cleanFlashcardAudio();
  const state = flashcards.snapshot(), card = state.card;
  $('flashcard-session').hidden = !card;
  $('flashcard-empty').hidden = Boolean(card);
  $('flashcard-stage').hidden = state.finished;
  $('flashcard-controls').hidden = state.finished;
  $('flashcard-completion').hidden = !state.finished;
  $('flashcard-answer').replaceChildren();
  $('flashcard-answer').hidden = !state.revealed;
  $('flashcard-front').textContent = '';
  if (!card) return;
  $('flashcard-progress').textContent = `${state.index + 1} / ${state.cards.length} cards · ${card.category} · ${card.level}`;
  $('flashcard-meter').max = state.cards.length; $('flashcard-meter').value = state.index + 1;
  $('flashcard-meter').setAttribute('aria-valuetext', `Card ${state.index + 1} of ${state.cards.length}`);
  const reverse = state.direction === 'en-ja';
  $('flashcard-prompt').textContent = reverse ? 'Recall the Japanese word' : card.category === 'kanji' ? 'Recall the meaning and a reading' : card.category === 'grammar' ? 'Recall how this pattern is used' : 'Recall the meaning';
  $('flashcard-front').textContent = reverse ? card.meaning : card.front;
  $('flashcard-front').setAttribute('lang', reverse ? 'en' : 'ja');
  $('flashcard-reveal').hidden = state.revealed;
  $('flashcard-prev').disabled = state.index === 0;
  $('flashcard-next').textContent = state.index === state.cards.length - 1 ? 'Finish session' : 'Next card';
  if (state.finished) {
    $('flashcard-completion-text').textContent = `Practice ended with ${state.cards.length} cards in this deck. Browsing is not a mastery assessment; no reviews or progress were saved.`;
    return;
  }
  if (state.revealed) {
    const answer = $('flashcard-answer');
    const heading = node('h3', reverse ? card.front : card.back, 'flashcard-answer-title'); heading.setAttribute('lang',reverse ? 'ja' : 'en');
    answer.append(heading);
    if (card.reading) { const reading = node('p',card.reading,'flashcard-reading'); reading.setAttribute('lang','ja'); answer.append(reading); }
    if (reverse) answer.append(node('p',card.meaning));
    if (card.explanation) answer.append(node('p',card.explanation));
    if (card.example_japanese) {
      const example = node('p',card.example_japanese,'flashcard-example'); example.setAttribute('lang','ja'); answer.append(example,node('p',card.example_translation,'small'));
    }
    // No activity callback: flashcard TTS never submits listening/mastery evidence.
    flashcardPlayer = attachJapaneseAudio(answer, card.category === 'vocabulary' ? card.front : card.example_japanese || card.front, 'Flashcard Japanese');
  }
}
function flashcardAction(action, focus = 'flashcard-front') { action(); renderFlashcard(); visibleFocus(focus); }
$('flashcard-deck').addEventListener('change', flashcardDirections);
$('flashcard-setup').addEventListener('submit', event => {
  event.preventDefault(); flashcards.start($('flashcard-deck').value,$('flashcard-direction').value); renderFlashcard(); visibleFocus('flashcard-front');
});
$('flashcard-reveal').addEventListener('click', () => flashcardAction(() => flashcards.reveal(),'flashcard-answer'));
$('flashcard-prev').addEventListener('click', () => flashcardAction(() => flashcards.move(-1)));
$('flashcard-next').addEventListener('click', () => flashcardAction(() => {
  const state = flashcards.snapshot(); if (state.index === state.cards.length - 1) flashcards.finish(); else flashcards.move(1);
}, flashcards.snapshot().index === flashcards.snapshot().cards.length - 1 ? 'flashcard-completion' : 'flashcard-front'));
$('flashcard-shuffle').addEventListener('click', () => flashcardAction(() => flashcards.restart(true)));
$('flashcard-restart').addEventListener('click', () => flashcardAction(() => flashcards.restart()));
$('flashcard-finish').addEventListener('click', () => flashcardAction(() => flashcards.finish(),'flashcard-completion'));
$('flashcard-again').addEventListener('click', () => flashcardAction(() => flashcards.restart()));
$('flashcard-again-shuffle').addEventListener('click', () => flashcardAction(() => flashcards.restart(true)));
window.addEventListener('hashchange', cleanFlashcardAudio);
window.addEventListener('pagehide', cleanFlashcardAudio);
document.addEventListener('learner-changed', () => { cleanFlashcardAudio(); flashcards.clear(); $('flashcard-session').hidden = true; });
flashcardDirections();
