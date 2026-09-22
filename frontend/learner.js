'use strict';

function remember(key, value) { try { if (value === null) localStorage.removeItem(`japanese-tutor-${key}`); else localStorage.setItem(`japanese-tutor-${key}`, value); } catch { /* Backend persistence still works. */ } }
function recalled(key) { try { return localStorage.getItem(`japanese-tutor-${key}`); } catch { return null; } }
function profileError(error) { $('profile-error').textContent = error.message; $('profile-error').hidden = false; }
const jsonOptions = (method, body) => ({method, headers: {'Content-Type': 'application/json'}, body: JSON.stringify(body)});

async function openSavedSession(id) {
  const saved = await api(`/api/learners/${placementLearnerId}/sessions/${id}`);
  sessionId = saved.session_id;
  savedSession = true;
  pendingChat = null;
  remember(`session-${placementLearnerId}`, sessionId);
  $('conversation').replaceChildren();
  if (!saved.turns.length) $('conversation').append(welcome.cloneNode(true));
  saved.turns.forEach(turn => { addMessage('learner', turn.message); renderReply(turn.response); });
  $('message').value = '';
  updateCount();
  $('status').textContent = saved.ended_at ? 'This session is closed. Choose New session to continue learning.' : `Saved session · Showing the latest ${saved.turns.length} of ${saved.interaction_count} exchanges.`;
}

async function activateLearner(id) {
  const profile = await api(`/api/learners/${encodeURIComponent(id)}/profile`);
  placementLearnerId = profile.learner_id;
  document.dispatchEvent(new Event('learner-changed'));
  sessionId = null;
  savedSession = false;
  pendingChat = null;
  $('conversation').replaceChildren(welcome.cloneNode(true));
  remember('learner', placementLearnerId);
  $('placement-context').textContent = `${profile.estimated_level} · Saved learner profile · Preferences and recent learning guide the tutor.`;
  $('level').value = profile.preferences.preferred_difficulty || profile.estimated_level.match(/N[1-5]/)?.[0] || 'beginner';
  const savedId = recalled(`session-${placementLearnerId}`);
  if (savedId) {
    try { await openSavedSession(savedId); return; }
    catch (error) { if (error.code !== 'saved_session_not_found') throw error; }
  }
  await resetSession();
}

function dateLabel(value) { return value ? new Date(value).toLocaleString() : 'No activity yet'; }
async function renderProfile() {
  $('profile-error').hidden = true;
  $('profile-details').hidden = !placementLearnerId;
  if (!placementLearnerId) { $('profile-summary').textContent = 'Complete placement or use beginner chat to create your learning profile.'; $('learner-identity').textContent = ''; return; }
  const id = placementLearnerId;
  const [profile, activity, sessions] = await Promise.all([
    api(`/api/learners/${id}/profile`), api(`/api/learners/${id}/activity`), api(`/api/learners/${id}/sessions`)
  ]);
  if (id !== placementLearnerId) return;
  $('profile-summary').textContent = `${profile.estimated_level} · ${profile.profile_source === 'default' ? 'No placement assessment yet' : 'Placement confidence ' + Math.round(profile.placement_confidence * 100) + '%'} · Last activity: ${dateLabel(profile.last_activity_at)}`;
  $('learner-identity').textContent = `Learner ID: ${id}. Keep this ID to reopen your profile on this server.`;
  const evidence = $('profile-evidence'); evidence.replaceChildren(node('h2', 'Your learning so far'));
  evidence.append(node('p', 'These summaries describe recent practice. Japanese Knowledge above estimates mastery across separate skills. A single error does not establish a weakness, and explanations alone do not establish understanding.', 'small'));
  const table = node('table'); const head = node('tr');
  ['Skill', 'Estimate', 'Recent performance'].forEach(text => head.append(node('th', text)));
  const thead = node('thead'); thead.append(head); table.append(thead);
  const tbody = node('tbody');
  Object.entries(profile.skills).forEach(([name, skill]) => {
    const row = node('tr'); row.append(node('th', name.replaceAll('_', ' ')), node('td', skill.estimated_level), node('td', skill.recent_count ? `${Math.round(skill.recent_average * 100)}% · ${skill.recent_count} observations` : 'Not enough evidence'));
    tbody.append(row);
  }); table.append(tbody); const scroll = node('div', undefined, 'table-scroll'); scroll.append(table); evidence.append(scroll);
  resultList(evidence, 'Needs practice', profile.weak_topics.map(t => t.display_name), 'No repeated weak areas identified yet.');
  resultList(evidence, 'Strengths', profile.strong_topics.map(t => t.display_name), 'More repeated evidence is needed.');
  resultList(evidence, 'Mistake patterns', profile.common_mistakes.map(t => `${t.display_name} · ${t.occurrences} occurrences · ${t.status}`), 'No mistake patterns recorded.');
  resultList(evidence, 'Recent topics', profile.recent_topics.map(t => `${t.display_name} · ${t.status.replaceAll('_', ' ')} · ${t.encounters} encounters`), 'Your studied topics will appear here.');
  for (const kind of ['vocabulary', 'grammar', 'kanji']) {
    resultList(evidence, `${kind[0].toUpperCase() + kind.slice(1)} memory`, profile.topic_memory.filter(t => t.topic_type === kind).map(t => `${t.display_name}${t.reading ? ' (' + t.reading + ')' : ''} · ${t.correct_count} correct / ${t.incorrect_count} incorrect · ${t.status.replaceAll('_', ' ')}`), 'No exposure recorded yet.');
  }
  if (profile.initial_placement) {
    const details = node('details'); details.append(node('summary', 'Original placement (preserved)'), node('p', `${profile.initial_placement.overall_estimate} · ${profile.initial_placement.recommended_starting_point}`)); evidence.append(details);
  }
  const prefs = profile.preferences;
  $('pref-romaji').checked = prefs.romaji_enabled; $('pref-furigana').checked = prefs.furigana_enabled;
  $('pref-language').value = prefs.explanation_language; $('pref-style').value = prefs.correction_style;
  $('pref-difficulty').value = prefs.preferred_difficulty || ''; $('pref-goal').value = prefs.primary_goal;
  const history = $('learning-history'); history.replaceChildren(node('h2', 'Recent sessions'));
  if (!sessions.length) history.append(node('p', 'No saved sessions yet.'));
  sessions.forEach(session => {
    const row = node('p'); row.append(node('span', `${dateLabel(session.started_at)} · ${session.interaction_count} exchanges · `));
    const button = node('button', session.ended_at ? 'View' : 'Resume', 'secondary'); button.type = 'button';
    button.addEventListener('click', async () => { if (busy) return; setBusy(true); try { await openSavedSession(session.session_id); showPanel('tutor'); } catch (error) { profileError(error); } finally { setBusy(false); } });
    row.append(button); history.append(row);
  });
  resultList(history, 'Recent activity', activity.map(event => `${dateLabel(event.created_at)} · ${event.event_type.replaceAll('_', ' ')}${event.topic ? ': ' + event.topic : ''}`), 'No activity recorded yet.');
  await renderMastery();
}

$('profile-tab').addEventListener('click', () => { showPanel('profile'); renderProfile().catch(profileError); });
$('restore-profile').addEventListener('submit', async event => {
  event.preventDefault(); if (busy) return; setBusy(true);
  try { await activateLearner($('learner-id').value.trim()); await renderProfile(); }
  catch (error) { profileError(error); } finally { setBusy(false); }
});
$('preferences-form').addEventListener('submit', async event => {
  event.preventDefault(); if (busy || !placementLearnerId) return; setBusy(true);
  try {
    const prefs = await api(`/api/learners/${placementLearnerId}/preferences`, jsonOptions('PATCH', {
      romaji_enabled: $('pref-romaji').checked, furigana_enabled: $('pref-furigana').checked,
      explanation_language: $('pref-language').value, correction_style: $('pref-style').value,
      preferred_difficulty: $('pref-difficulty').value || null, primary_goal: $('pref-goal').value
    }));
    const current = await api(`/api/learners/${placementLearnerId}/profile`);
    $('level').value = prefs.preferred_difficulty || current.estimated_level.match(/N[1-5]/)?.[0] || 'beginner';
    $('profile-notice').textContent = 'Preferences saved. They apply to your next tutor message.';
  } catch (error) { profileError(error); } finally { setBusy(false); }
});
$('level').addEventListener('change', async () => {
  if (!placementLearnerId) return;
  try { await api(`/api/learners/${placementLearnerId}/preferences`, jsonOptions('PATCH', {preferred_difficulty: $('level').value})); }
  catch (error) { showError(error); }
});
$('temporary-chat').addEventListener('click', async () => {
  if (busy) return;
  placementLearnerId = null; sessionId = null; savedSession = false; remember('learner', null);
  document.dispatchEvent(new Event('learner-changed'));
  $('placement-context').textContent = 'Temporary chat · No learning profile selected.';
  $('level').value = 'beginner'; await resetSession(); showPanel('tutor');
});
(async () => {
  const id = recalled('learner');
  if (id) { try { await activateLearner(id); } catch (error) { showPanel('profile'); profileError(error); } }
  else await resetSession();
})();
