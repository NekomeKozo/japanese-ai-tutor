'use strict';

let jlptState = null, jlptOwner = null, jlptBusy = false, jlptCatalog = null;
let jlptStartPending = null, jlptAnswerPending = null, jlptFeedbackShown = false;
let jlptRenderedQuestion = null, jlptTimer = null, jlptRemainingAt = null, jlptSyncedAt = 0;
let jlptLoadSequence = 0;
const jlptBase = () => `/api/learners/${placementLearnerId}/jlpt`;
const jlptPath = () => `${jlptBase()}/sessions/${jlptState.session_id}`;

function jlptError(error) {
  $('jlpt-error').textContent = friendlyError(error); $('jlpt-error').hidden = false; $('jlpt-retry').hidden = false;
}
function jlptAccept(state, showFeedback = true) {
  jlptState = state; jlptOwner = placementLearnerId;
  jlptFeedbackShown = Boolean(showFeedback && state?.feedback);
  jlptRemainingAt = state?.remaining_seconds ?? null; jlptSyncedAt = Date.now();
  renderJLPT();
}
async function jlptAction(action) {
  if (jlptBusy || busy) return;
  const owner = placementLearnerId; jlptBusy = true;
  $('jlpt-error').hidden = true; $('jlpt-retry').hidden = true;
  $('jlpt-status').textContent = 'Saving your practice…';
  $('jlpt-panel').setAttribute('aria-busy', 'true');
  const controls = $('jlpt-panel').querySelectorAll('button,input,select'); controls.forEach(c => { c.disabled = true; });
  try { await action(owner); if (owner === placementLearnerId) $('jlpt-status').textContent = 'Saved. You can return to this practice later.'; }
  catch (error) { if (owner === placementLearnerId) { jlptError(error); $('jlpt-status').textContent = 'Your answer is still here. Retry to save it.'; } }
  finally {
    jlptBusy = false; controls.forEach(c => { c.disabled = false; });
    $('jlpt-panel').setAttribute('aria-busy', 'false'); jlptModeOptions();
  }
}
async function loadJLPT(force = false) {
  const owner = placementLearnerId, sequence = ++jlptLoadSequence;
  if (!owner) { jlptState = null; renderJLPT(); return; }
  if (!force && jlptOwner === owner) { jlptTick(); return; }
  $('jlpt-status').textContent = 'Loading saved practice…'; $('jlpt-error').hidden = true; $('jlpt-retry').hidden = true;
  const [catalog, active, initialHistory] = await Promise.all([
    jlptCatalog || api('/api/jlpt/catalog'), api(`${jlptBase()}/sessions/active`), api(`${jlptBase()}/history`)
  ]);
  if (owner !== placementLearnerId || sequence !== jlptLoadSequence) return;
  // Resolving an expired active session completes it. The parallel history read
  // may have run before that transaction, so refresh only after this transition.
  const history = active?.status === 'completed' ? await api(`${jlptBase()}/history`) : initialHistory;
  if (owner !== placementLearnerId || sequence !== jlptLoadSequence) return;
  jlptCatalog = catalog; jlptAccept(active); renderJLPTHistory(history); $('jlpt-status').textContent = '';
}
function jlptModeOptions() {
  const mock = $('jlpt-mode').value === 'mock';
  if (mock) $('jlpt-section').value = 'mixed';
  if ($('jlpt-mode').value === 'focused' && $('jlpt-section').value === 'mixed') $('jlpt-section').value = 'vocabulary';
  $('jlpt-section').disabled = mock || jlptBusy;
  $('jlpt-mode-note').textContent = mock ? 'Mock: answers and explanations are shown only after you finish. Unanswered questions count as incorrect in practice accuracy.' : 'Practice gives feedback after each answer. Weakness practice uses repeated evidence; a balanced set is used when evidence is limited.';
}
function jlptTick() {
  if (!jlptState || jlptState.status !== 'in_progress' || jlptRemainingAt === null) return;
  const left = Math.max(0, jlptRemainingAt - Math.floor((Date.now()-jlptSyncedAt)/1000));
  $('jlpt-timer').textContent = `Time remaining: ${Math.floor(left/60)}:${String(left%60).padStart(2,'0')}`;
  if (left === 0 && !jlptBusy) {
    clearInterval(jlptTimer); jlptTimer = null;
    jlptAction(async owner => { const state = await api(jlptPath()); if (owner === placementLearnerId) { jlptAccept(state); $('jlpt-status').textContent = 'Time is up. Your saved answers are included in the results.'; } });
  }
}
function jlptReviewCard(item, container) {
  container.append(node('h3', item.answer === null ? 'Not answered' : item.correct ? 'Correct' : 'Worth another look'),
    node('p', item.prompt), node('p', `Your answer: ${item.answer ?? 'Not answered'}`),
    node('p', `Correct answer: ${item.correct_answers.join(' / ')}`), node('p', item.explanation));
  if (item.passage_text) { const p = node('p', item.passage_text, 'jlpt-passage'); p.lang = 'ja'; container.append(p); }
  const ask = node('button', 'Ask Tutor about this', 'secondary'); ask.type = 'button';
  ask.addEventListener('click', () => jlptAsk(item)); container.append(ask);
}
async function jlptAsk(item) {
  return jlptAction(async owner => {
    if ($('message').value.trim()) throw new Error('Your Tutor draft is still saved. Send or clear it before opening this explanation.');
    await api(`${jlptPath()}/explanations/${item.id}`, {method:'POST'});
    if (owner !== placementLearnerId) return;
    // Opening a new Tutor session clears its composer; initialize it before filling the follow-up.
    await ensureTutorSession();
    if (owner !== placementLearnerId) return;
    if (practiceState?.status === 'completed') await resetSession();
    if (!sessionId) throw new Error('The Tutor could not open. Please retry this explanation.');
    const text = `Please explain this Japanese practice question: ${item.prompt.slice(0,800)}\n${item.passage_text ? 'Original practice passage: '+item.passage_text.slice(0,1000)+'\n' : ''}Correct answer: ${item.correct_answers.join(' / ')}\nExplanation: ${item.explanation.slice(0,500)}`;
    $('message').value = text; $('mode').value = 'chat'; updateCount();
    showPanel('tutor');
  });
}
function renderJLPT() {
  if (jlptTimer) clearInterval(jlptTimer); jlptTimer = null;
  const active = jlptState?.status === 'in_progress';
  $('jlpt-empty').hidden = Boolean(placementLearnerId); $('jlpt-setup').hidden = !placementLearnerId || active;
  $('jlpt-session').hidden = !active; $('jlpt-results').hidden = jlptState?.status !== 'completed';
  if (!active) jlptRenderedQuestion = null;
  if (active) {
    const s = jlptState, q = s.question;
    $('jlpt-progress').textContent = `${s.level} · ${readable(s.mode)} · ${s.answered_count} of ${s.question_count} answered`;
    $('jlpt-meter').max = s.question_count; $('jlpt-meter').value = s.answered_count;
    $('jlpt-timer').textContent = 'Untimed practice';
    $('jlpt-finish-note').textContent = `${s.question_count-s.answered_count} unanswered. Finishing now counts these as incorrect. Ending without results keeps the history; submitted practice evidence is retained.`;
    $('jlpt-answer-form').hidden = !q || jlptFeedbackShown;
    $('jlpt-feedback').hidden = !jlptFeedbackShown; $('jlpt-next').hidden = !jlptFeedbackShown || !q;
    if (jlptFeedbackShown) { $('jlpt-feedback').replaceChildren(); jlptReviewCard(s.feedback, $('jlpt-feedback')); }
    if (q && q.id !== jlptRenderedQuestion) {
      jlptRenderedQuestion = q.id; $('jlpt-answer').value = ''; jlptAnswerPending = null;
      $('jlpt-question-title').textContent = `Question ${s.answered_count+1} · ${readable(q.section)}`;
      $('jlpt-prompt').textContent = q.prompt; $('jlpt-passage').textContent = q.passage_text || ''; $('jlpt-passage').hidden = !q.passage_text;
      const choices = $('jlpt-choices'); choices.replaceChildren(node('legend', 'Choose one answer')); choices.hidden = !q.choices.length;
      q.choices.forEach((choice, index) => {
        const label = node('label', undefined, 'jlpt-choice'), input = node('input');
        input.type = 'radio'; input.name = 'jlpt-choice'; input.value = choice; input.required = true; input.id = `jlpt-choice-${index}`;
        input.addEventListener('change', () => { $('jlpt-answer').value = choice; });
        label.append(input, node('span', choice)); choices.append(label);
      });
      $('jlpt-answer-label').hidden = Boolean(q.choices.length); $('jlpt-answer').hidden = Boolean(q.choices.length);
      $('jlpt-answer').required = !q.choices.length;
      $('jlpt-submit').textContent = s.mode === 'mock' ? 'Save answer' : 'Check answer';
    }
    if (jlptRemainingAt !== null) { jlptTimer = setInterval(jlptTick, 1000); jlptTick(); }
  }
  if (jlptState?.status === 'completed') {
    const s = jlptState, r = s.result, panel = $('jlpt-results');
    panel.replaceChildren(node('h2', 'Your practice results'), node('p', `${r.correct} of ${r.total} correct · ${r.accuracy}% practice accuracy`, 'stat-value'), node('p', r.note, 'small'), node('p', `${r.answered} answered · ${Math.floor(s.elapsed_seconds/60)} min ${s.elapsed_seconds%60} sec`));
    const breakdown = node('ul'); Object.entries(r.sections).forEach(([name, score]) => breakdown.append(node('li', `${readable(name)}: ${score.correct}/${score.total} · ${score.accuracy}%`))); panel.append(breakdown);
    resultList(panel, 'Answered correctly', r.done_well, 'Keep practicing; one session is only a small sample.');
    resultList(panel, 'Worth reviewing', r.needs_review, 'No answered questions were incorrect.');
    const review = node('section'); review.append(node('h3', 'Review your questions'));
    s.review.forEach((item, index) => {
      const detail = node('details'); detail.append(node('summary', `${index+1}. ${readable(item.section)} · ${item.answer === null ? 'Not answered' : item.correct ? 'Correct' : 'Review'}`));
      jlptReviewCard(item, detail);
      detail.addEventListener('toggle', () => { if (detail.open) api(`${jlptPath()}/explanations/${item.id}`, {method:'POST'}).catch(jlptError); });
      review.append(detail);
    }); panel.append(review);
  }
  jlptModeOptions();
}
function renderJLPTHistory(history) {
  const panel = $('jlpt-history'); panel.replaceChildren();
  if (!history.length) { panel.append(node('p', 'Your first practice will appear here.')); return; }
  history.forEach(item => {
    const row = node('div', undefined, 'jlpt-history-row');
    row.append(node('p', `${item.level} · ${readable(item.mode)} · ${readable(item.status)}${item.accuracy === null ? '' : ` · ${item.accuracy}%`} · ${dateLabel(item.started_at)}`));
    const open = node('button', item.status === 'in_progress' ? 'Resume' : 'Open', 'secondary'); open.type = 'button';
    open.addEventListener('click', () => jlptAction(async owner => { const state = await api(`${jlptBase()}/sessions/${item.session_id}`); if (owner === placementLearnerId) { jlptAccept(state); visibleFocus(state.status === 'completed' ? 'jlpt-results' : 'jlpt-question-title'); } }));
    row.append(open); panel.append(row);
  });
}
async function jlptRefreshHistory(owner) {
  const history = await api(`${jlptBase()}/history`); if (owner === placementLearnerId) renderJLPTHistory(history);
}
$('jlpt-mode').addEventListener('change', jlptModeOptions);
$('jlpt-setup').addEventListener('submit', event => {
  event.preventDefault(); return jlptAction(async owner => {
    const selection = {level:$('jlpt-level').value,mode:$('jlpt-mode').value,section:$('jlpt-section').value,timed:$('jlpt-timed').checked};
    if (selection.mode === 'focused' && selection.section === 'mixed') throw new Error('Choose vocabulary, kanji, grammar or reading for section practice.');
    const signature = JSON.stringify(selection);
    if (jlptStartPending?.signature !== signature) jlptStartPending = {signature, body:{...selection,request_id:crypto.randomUUID()}};
    const state = await api(`${jlptBase()}/sessions`, jsonOptions('POST',jlptStartPending.body));
    if (owner !== placementLearnerId) return;
    jlptStartPending = null; jlptAccept(state); visibleFocus('jlpt-question-title'); await jlptRefreshHistory(owner);
  });
});
$('jlpt-answer-form').addEventListener('submit', event => {
  event.preventDefault(); return jlptAction(async owner => {
    const answer = $('jlpt-answer').value, q = jlptState.question;
    if (!answer.trim()) throw new Error('Choose an answer or enter the reading.');
    const signature = `${jlptState.session_id}:${q.id}:${answer}`;
    if (jlptAnswerPending?.signature !== signature) jlptAnswerPending = {signature, body:{question_id:q.id,answer,submission_id:crypto.randomUUID()}};
    const state = await api(`${jlptPath()}/answer`, jsonOptions('POST',jlptAnswerPending.body));
    if (owner !== placementLearnerId) return;
    jlptAnswerPending = null; jlptAccept(state);
    visibleFocus(state.status === 'completed' ? 'jlpt-results' : jlptFeedbackShown ? 'jlpt-feedback' : state.question ? 'jlpt-question-title' : 'jlpt-finish');
  });
});
$('jlpt-next').addEventListener('click', () => { jlptFeedbackShown = false; renderJLPT(); visibleFocus('jlpt-question-title'); });
for (const action of ['finish','abandon']) $(`jlpt-${action}`).addEventListener('click', () => jlptAction(async owner => {
  const state = await api(`${jlptPath()}/${action}`, {method:'POST'});
  if (owner === placementLearnerId) { jlptAccept(state); await jlptRefreshHistory(owner); visibleFocus(action === 'finish' ? 'jlpt-results' : 'jlpt-start'); }
}));
$('jlpt-retry').addEventListener('click', () => jlptAction(() => loadJLPT(true)));
document.addEventListener('learner-changed', () => {
  ++jlptLoadSequence; if (jlptTimer) clearInterval(jlptTimer); jlptTimer = null;
  jlptState = null; jlptOwner = null; jlptRenderedQuestion = null; jlptStartPending = null; jlptAnswerPending = null;
  $('jlpt-history').replaceChildren(); $('jlpt-results').replaceChildren(); renderJLPT();
});
