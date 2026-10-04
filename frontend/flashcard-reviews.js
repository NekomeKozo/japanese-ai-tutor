'use strict';

// Confirmed backend receipts are the only source of completed counts.
let dueFlashcards = freshDueFlashcards();
let dueGeneration = 0;
let dueHistoryRequest = 0;
function freshDueFlashcards() {
  return {items:[], index:0, revealed:false, loaded:false, loading:false, saving:false,
    completed:new Set(), total:0, unsupported:0, pending:null, error:'', changed:false, learner:null};
}
const recallLabels = ['again','hard','good','easy'];
function dueOpen() { return flashcardMode === 'due' && location.hash === '#study/flashcards'; }
function renderDueFlashcard() {
  const state = dueFlashcards, item = state.items[state.index];
  cleanFlashcardAudio();
  $('flashcard-empty').hidden = true;
  $('flashcard-session').hidden = !item || state.loading || !placementLearnerId;
  $('flashcard-stage').hidden = false;
  $('flashcard-controls').hidden = true;
  $('flashcard-completion').hidden = true;
  $('flashcard-ratings').hidden = !item || !state.revealed || state.loading;
  $('flashcard-due-profile').hidden = Boolean(placementLearnerId);
  $('flashcard-due-error').hidden = !state.error;
  $('flashcard-due-error').textContent = state.error;
  $('flashcard-due-retry').hidden = !state.pending || !state.error || state.changed;
  $('flashcard-due-retry').disabled = state.saving;
  $('flashcard-due-load').disabled = state.loading || state.saving || Boolean(state.pending && !state.changed);
  for (const mode of ['free','due']) $('flashcard-mode-'+mode).disabled = state.saving;
  for (const label of recallLabels) $('flashcard-rate-'+label).disabled = !state.revealed || state.saving || Boolean(state.pending) || state.changed;
  $('flashcard-session').setAttribute('aria-busy',String(state.saving));
  const remaining = Math.max(0,state.total-state.completed.size);
  const summary = `${state.completed.size} completed · ${remaining} scheduled targets remaining.`;
  $('flashcard-due-status').textContent = !placementLearnerId ? 'Due Reviews need a learner profile.' : state.loading ? 'Loading your Due Reviews…' : state.saving ? 'Saving your rating…' : !state.loaded ? 'Load your scheduled cards to begin.' : item ? `${summary} ${state.items.length-state.index} cards in this batch.` : state.completed.size ? `Batch complete! ${summary} Reload for more, or continue with Free Practice.` : 'You’re all caught up! No eligible flashcards are due right now. Try Free Practice or return later.';
  if (state.loaded && state.unsupported) $('flashcard-due-status').textContent += ` ${state.unsupported} other targets use Daily Study & Review.`;
  if (!item || state.loading || !placementLearnerId) { $('flashcard-answer').replaceChildren(); return; }
  $('flashcard-progress').textContent = `${state.index+1} / ${state.items.length} · ${item.card.category} · ${item.dimension.replaceAll('_',' ')}`;
  $('flashcard-meter').max = state.items.length; $('flashcard-meter').value = state.completed.size;
  $('flashcard-meter').setAttribute('aria-label','Confirmed reviews in this batch');
  $('flashcard-meter').setAttribute('aria-valuetext',`${state.completed.size} of ${state.items.length} saved`);
  renderFlashcardFace(item.card,state.revealed,false,true);
}
async function loadDueHistory(learner, generation) {
  const request = ++dueHistoryRequest;
  try {
    const data = await api(`/api/learners/${learner}/reviews/history`);
    if (request !== dueHistoryRequest || generation !== dueGeneration || placementLearnerId !== learner) return;
    const list = $('flashcard-due-history'); list.replaceChildren();
    if (!data.items.length) list.append(node('p','No saved reviews yet.','small'));
    for (const item of data.items) list.append(node('p',`${item.title} · ${item.dimension.replaceAll('_',' ')} · ${item.rating} · ${item.method === 'self_report' ? 'self-assessment' : 'graded exercise'} · ${new Date(item.reviewed_at).toLocaleString()}`,'small'));
  } catch (error) {
    if (request === dueHistoryRequest && generation === dueGeneration && placementLearnerId === learner) $('flashcard-due-history').replaceChildren(node('p','History could not load. Reload Due Reviews to retry.','small'));
  }
}
async function loadDueFlashcards() {
  if (dueFlashcards.saving || dueFlashcards.pending && !dueFlashcards.changed) return;
  const learner = placementLearnerId, generation = ++dueGeneration;
  dueFlashcards = freshDueFlashcards(); dueFlashcards.learner = learner;
  $('flashcard-due-history').replaceChildren();
  if (!learner) { renderDueFlashcard(); return; }
  dueFlashcards.loading = true; renderDueFlashcard();
  loadDueHistory(learner,generation);
  try {
    const data = await api(`/api/learners/${learner}/reviews/flashcards`);
    if (generation !== dueGeneration || placementLearnerId !== learner) return;
    dueFlashcards.items = data.items; dueFlashcards.total = data.due_count;
    dueFlashcards.unsupported = data.unsupported_count; dueFlashcards.loaded = true;
  } catch (error) {
    if (generation !== dueGeneration || placementLearnerId !== learner) return;
    dueFlashcards.error = friendlyError(error);
  } finally {
    if (generation === dueGeneration && placementLearnerId === learner) { dueFlashcards.loading = false; if (dueOpen()) renderDueFlashcard(); }
  }
}
async function saveFlashcardRating(label) {
  const state = dueFlashcards, item = state.items[state.index];
  if (!item || !state.revealed || state.saving || state.changed || state.learner !== placementLearnerId) return;
  if (!state.pending && !recallLabels.includes(label)) return;
  const generation = dueGeneration, learner = state.learner;
  // Preserve the exact request after an ambiguous failure, including its UUID.
  state.pending ||= {submission_id:crypto.randomUUID(), version:item.version, rating:label};
  state.saving = true; state.error = ''; if (dueOpen()) renderDueFlashcard();
  try {
    const receipt = await api(`/api/learners/${learner}/reviews/${item.review_id}/recall`,jsonOptions('POST',state.pending));
    if (generation !== dueGeneration || placementLearnerId !== learner) return;
    if (!receipt.completed || receipt.review_id !== item.review_id || receipt.submission_id !== state.pending.submission_id) throw new Error('The save could not be confirmed. Retry this rating.');
    state.completed.add(receipt.submission_id); state.pending = null;
    state.index++; state.revealed = false;
    loadDueHistory(learner,generation);
  } catch (error) {
    if (generation !== dueGeneration || placementLearnerId !== learner) return;
    state.changed = ['review_changed','review_conflict','review_not_found','review_unsupported'].includes(error.code);
    state.error = friendlyError(error) + (state.changed ? ' Reload Due Reviews to continue.' : ' Nothing is counted until saving is confirmed. Retry saving this rating.');
  } finally {
    if (generation === dueGeneration && placementLearnerId === learner) {
      state.saving = false;
      if (dueOpen()) { renderDueFlashcard(); visibleFocus(state.error ? 'flashcard-due-error' : state.items[state.index] ? 'flashcard-front' : 'flashcard-due-status'); }
    }
  }
}
function setFlashcardMode(mode) {
  if (dueFlashcards.saving) return;
  flashcardMode = mode; cleanFlashcardAudio();
  $('flashcard-free-options').hidden = mode !== 'free';
  $('flashcard-due-options').hidden = mode !== 'due';
  for (const name of ['free','due']) {
    $('flashcard-mode-'+name).setAttribute('aria-pressed',String(name===mode));
    $('flashcard-mode-'+name).className = name===mode ? '' : 'secondary';
  }
  $('flashcard-ratings').hidden = true;
  if (mode === 'due') { if (!dueFlashcards.loaded && !dueFlashcards.loading) loadDueFlashcards(); else renderDueFlashcard(); }
  else { $('flashcard-controls').hidden = false; $('flashcard-meter').setAttribute('aria-label','Current card position'); loadFlashcards(); }
}
for (const label of recallLabels) $('flashcard-rate-'+label).addEventListener('click',()=>saveFlashcardRating(label));
$('flashcard-mode-free').addEventListener('click',()=>setFlashcardMode('free'));
$('flashcard-mode-due').addEventListener('click',()=>setFlashcardMode('due'));
$('flashcard-due-load').addEventListener('click',loadDueFlashcards);
$('flashcard-due-retry').addEventListener('click',()=>saveFlashcardRating());
document.addEventListener('learner-changed',()=>{
  dueGeneration++; dueFlashcards = freshDueFlashcards();
  for (const mode of ['free','due']) $('flashcard-mode-'+mode).disabled = false;
  $('flashcard-due-history').replaceChildren();
  if (dueOpen()) loadDueFlashcards();
});
