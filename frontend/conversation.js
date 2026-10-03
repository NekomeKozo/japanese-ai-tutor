'use strict';
let practiceState = null;
let scenarioCatalog = [];
let practiceLoading = false;

function practiceError(error) {
  $('practice-error').textContent = friendlyError(error);
  $('practice-error').hidden = false;
  $('practice-retry').hidden = Boolean(scenarioCatalog.length);
}
function practiceControls() {
  const active = practiceState?.status === 'active';
  const completed = practiceState?.status === 'completed';
  $('practice-setup').hidden = Boolean(active);
  $('practice-active').hidden = !active;
  $('practice-recap').hidden = !completed;
  $('practice-profile-note').hidden = Boolean(placementLearnerId);
  for (const id of ['practice-scenario','practice-policy','practice-start']) $(id).disabled = busy || practiceLoading || !placementLearnerId || !scenarioCatalog.length;
  $('practice-finish').disabled = busy;
  $('reset').hidden = Boolean(active) || $('tutor-panel').hidden;
  $('tutor-level-controls').hidden = Boolean(active);
  $('mode').hidden = Boolean(active);
  $('mode-label').hidden = Boolean(active);
  $('chat-form').hidden = Boolean(completed);
  if (active) $('mode').value = 'chat';
  voiceReplyControls();
}
function scenarioDescription() {
  const selected = scenarioCatalog.find(item => item.key === $('practice-scenario').value);
  $('practice-description').textContent = selected ? `${selected.description} Suggested starting point: ${selected.minimum_level}. We adapt the language to you.` : '';
}
async function loadScenarioCatalog() {
  if (!placementLearnerId || scenarioCatalog.length || practiceLoading) return;
  practiceLoading = true; practiceControls();
  $('practice-loading').hidden = false;
  try {
    scenarioCatalog = await api('/api/conversation/scenarios');
    $('practice-scenario').replaceChildren();
    scenarioCatalog.forEach(item => { const option = node('option', item.title); option.value = item.key; $('practice-scenario').append(option); });
    $('practice-scenario').value = scenarioCatalog[0]?.key || '';
    scenarioDescription(); $('practice-error').hidden = true; $('practice-retry').hidden = true;
  } catch (error) { practiceError(error); }
  finally { practiceLoading = false; $('practice-loading').hidden = true; practiceControls(); }
}
function applyPractice(state) {
  voicePracticeChanged(state);
  practiceState = state || null;
  if (state) {
    $('practice-title').textContent = state.scenario.title;
    $('practice-goal').textContent = state.scenario.goal;
    $('practice-difficulty').textContent = `Practice difficulty: ${state.effective_level} · ${readable(state.correction_policy)} corrections. This is not a placement result.`;
    if (state.recap) {
      const recap = state.recap;
      $('practice-recap-content').replaceChildren(node('p', `${state.scenario.title} · ${recap.turn_count} learner turns`),
        node('p', `Final practice difficulty: ${recap.final_effective_level}`),
        node('p', recap.topics.length ? `Recorded topics: ${recap.topics.join(', ')}` : 'No topic evidence recorded yet.'),
        node('p', `${recap.observations} recorded observations. These are provisional learning evidence.`),
        node('p', recap.recent_performance_average === null ? 'Not enough scored evidence to summarize performance.' : `Recent recorded performance: ${Math.round(recap.recent_performance_average * 100)}% across ${recap.scored_turns} scored turns. This is not a proficiency score.`));
    }
  }
  practiceControls();
}
async function restoreActivePractice() {
  if (!placementLearnerId) return false;
  const state = await api(`/api/learners/${placementLearnerId}/conversations/active`);
  if (!state) return false;
  await openSavedSession(state.session_id);
  return true;
}
async function refreshPractice() {
  if (!practiceState || !placementLearnerId) return;
  try {
    const saved = await api(`/api/learners/${placementLearnerId}/conversations/${sessionId}`);
    applyPractice(saved.conversation);
  } catch (error) { practiceError(error); }
}
$('practice-scenario').addEventListener('change', scenarioDescription);
$('practice-retry').addEventListener('click', loadScenarioCatalog);
$('practice-start').addEventListener('click', async () => {
  if (busy || !placementLearnerId) return;
  setBusy(true); $('practice-error').hidden = true; $('error').hidden = true;
  try {
    const state = await api(`/api/learners/${placementLearnerId}/conversations`, jsonOptions('POST', {
      scenario_key: $('practice-scenario').value, correction_policy: $('practice-policy').value
    }));
    await openSavedSession(state.session_id);
  } catch (error) {
    if (error.code === 'conversation_active') {
      try { await restoreActivePractice(); } catch (restoreError) { practiceError(restoreError); }
    } else practiceError(error);
  } finally { setBusy(false); visibleFocus('message'); }
});
$('practice-finish').addEventListener('click', async () => {
  if (busy || practiceState?.status !== 'active') return;
  japaneseAudio.stop(); clearVoiceReply();
  setBusy(true); $('practice-error').hidden = true;
  try {
    applyPractice(await api(`/api/learners/${placementLearnerId}/conversations/${sessionId}/finish`, {method:'POST'}));
    pendingChat = null; $('status').textContent = 'Conversation saved. Your recap is below.';
    visibleFocus('practice-recap-title');
  } catch (error) { practiceError(error); }
  finally { setBusy(false); }
});
document.addEventListener('learner-changed', () => { applyPractice(null); });
