'use strict';

const routes = ['home', 'study', 'tutor', 'progress', 'settings', 'placement'];
let appReady = false;
let booting = false;
let routeRequest = 0;
let settingsLearner = null;
let settingsDirty = false;
let homeNext = 'placement';

function readable(value) { return String(value || '').replaceAll('_', ' '); }
function visibleFocus(id) { const element = $(id); if (element && !element.closest('[hidden]')) element.focus(); }
function showPanel(which) {
  const route = which === 'profile' ? 'progress' : which;
  if (location.hash.slice(1) === route) renderRoute();
  else location.hash = route;
}
function currentRoute() {
  const [section, detail] = location.hash.slice(1).split('/');
  return {section: routes.includes(section) ? section : 'home', detail};
}
function progressSection(detail) {
  const selected = ['overview','skills','knowledge','history'].includes(detail) ? detail : 'overview';
  const ids = {overview:'progress-overview', skills:'profile-evidence', knowledge:'progress-knowledge', history:'learning-history'};
  Object.entries(ids).forEach(([key, id]) => { $(id).hidden = key !== selected; });
  document.querySelectorAll('.section-nav a').forEach(a => a.setAttribute('aria-current', a.hash === `#progress/${selected}` ? 'page' : 'false'));
}
async function renderRoute() {
  const sequence = ++routeRequest;
  const {section, detail} = currentRoute();
  routes.forEach(route => { $(`${route === 'progress' ? 'profile' : route}-panel`).hidden = route !== section || (!appReady && (section !== 'settings' || booting)); });
  document.querySelectorAll('.primary-nav a,.secondary-nav a').forEach(a => a.setAttribute('aria-current', a.hash === `#${section}` ? 'page' : 'false'));
  $('page-title').textContent = {home:'Home',study:'Today’s study',tutor:'Your Japanese tutor',progress:'Your progress',settings:'Settings',placement:'Your starting point'}[section];
  document.title = 'GoiGrow — Japanese Tutor';
  $('reset').hidden = section !== 'tutor' || !appReady;
  if (!appReady && (section !== 'settings' || booting)) return;
  visibleFocus('page-title');
  speakingRoute(section === 'study' && detail === 'speaking');
  voiceReplyControls();
  try {
    if (section === 'home') await renderHome();
    if (section === 'study') {
      const jlpt = detail === 'jlpt', listening = detail === 'listening', speaking = detail === 'speaking';
      $('personalized-study').hidden = jlpt || listening || speaking; $('jlpt-panel').hidden = !jlpt; $('listening-panel').hidden = !listening; $('speaking-panel').hidden = !speaking;
      document.querySelectorAll('.study-nav a').forEach(a => a.setAttribute('aria-current', a.hash === (jlpt ? '#study/jlpt' : listening ? '#study/listening' : speaking ? '#study/speaking' : '#study') ? 'page' : 'false'));
      if (jlpt) await loadJLPT(); else if (!listening && !speaking) await loadStudy();
    }
    if (section === 'progress') { progressSection(detail); await renderProfile(); }
    if (section === 'settings') await loadSettings();
    if (section === 'tutor' && !sessionId) await ensureTutorSession();
    if (section === 'tutor') { await loadScenarioCatalog(); practiceControls(); }
  } catch (error) {
    if (sequence !== routeRequest) return;
    if (section === 'progress') profileError(error);
    else if (section === 'study') { if (detail === 'jlpt') jlptError(error); else studyError(error); }
    else if (section === 'settings') settingsError(error);
    else showAppError(error);
  }
}
function showAppError(error) {
  $('app-error-text').textContent = friendlyError(error);
  $('app-error').hidden = false;
}
function settingsError(error) { $('settings-error').textContent = friendlyError(error); $('settings-error').hidden = false; $('settings-retry').hidden = false; }
async function loadSettings() {
  $('settings-error').hidden = true; $('settings-retry').hidden = true;
  $('settings-empty').hidden = Boolean(placementLearnerId);
  $('preferences-form').hidden = !placementLearnerId;
  $('settings-loading').hidden = true;
  if (!placementLearnerId) return;
  if (settingsLearner === placementLearnerId && settingsDirty) return;
  const id = placementLearnerId;
  $('settings-loading').hidden = false;
  $('preferences-form').hidden = true;
  try {
    const profile = await api(`/api/learners/${id}/profile`);
    if (id !== placementLearnerId) return;
    const prefs = profile.preferences;
    $('pref-romaji').checked = prefs.romaji_enabled; $('pref-furigana').checked = prefs.furigana_enabled;
    $('pref-language').value = prefs.explanation_language; $('pref-style').value = prefs.correction_style;
    $('pref-difficulty').value = prefs.preferred_difficulty || ''; $('pref-goal').value = prefs.primary_goal;
    $('learner-identity').textContent = `Your saved profile ID: ${id}`;
    settingsLearner = id; settingsDirty = false; $('preferences-form').hidden = false;
  } finally { $('settings-loading').hidden = true; }
}
function chooseNextAction({learner, assessment, active, due}) {
  if (assessment?.status === 'in_progress') return 'placement';
  if (!learner) return 'placement';
  if (active && ['planned','in_progress'].includes(active.status)) return 'continue';
  return due > 0 ? 'review' : 'study';
}
let homeRequest = 0;
async function renderHome() {
  const sequence = ++homeRequest;
  const id = placementLearnerId;
  $('home-loading').hidden = false; $('home-content').hidden = true; $('app-error').hidden = true;
  try {
    let profile = null, queue = null, active = null, activity = [];
    if (id) [profile, queue, active, activity] = await Promise.all([
      api(`/api/learners/${id}/profile`), api(`/api/learners/${id}/reviews/due?minutes=10`),
      api(`/api/learners/${id}/study/active`), api(`/api/learners/${id}/activity?limit=3`)
    ]);
    if (sequence !== homeRequest || id !== placementLearnerId) return;
    homeNext = chooseNextAction({learner:profile, assessment:assessmentState, active, due:queue?.due_count});
    const unfinished = assessmentState?.status === 'in_progress';
    const copy = {
      placement: [unfinished ? 'Pick up where you left off.' : 'Make room for a little Japanese.', unfinished ? 'Your placement answers are saved. Let’s keep finding the right starting point.' : 'Find a comfortable starting point, or begin with the basics. Your learning will adapt as you practice.', unfinished ? 'Continue placement' : 'Find my starting point'],
      continue: ['Your next step is waiting.', 'Your saved study plan is ready. Continue at your own pace.', 'Continue my study'],
      review: ['A little review goes a long way.', `${queue?.due_count || 0} items are ready to revisit. A short session helps keep them familiar.`, 'Start daily review'],
      study: ['Let’s build on what you know.', 'Choose a little time for Japanese. Your plan will reflect your practice and learning goal.', 'Plan today’s study']
    }[homeNext];
    $('home-headline').textContent = copy[0]; $('home-description').textContent = copy[1]; $('home-action').textContent = copy[2];
    $('home-action-note').textContent = homeNext === 'continue' ? `${active.estimated_minutes} minute plan · ${active.activities.filter(a=>['completed','skipped'].includes(a.status)).length} of ${active.activities.length} activities finished` : homeNext === 'review' ? `About ${queue.selected_minutes} minutes in a 10-minute review window` : 'A small step is enough for today.';
    const stats = $('home-stats'); stats.replaceChildren();
    if (profile) {
      for (const [label, value] of [['Study estimate', profile.estimated_level],['Learning goal', readable(profile.preferences.primary_goal)],['Ready for review', String(queue.due_count)]]) {
        const card = node('section', undefined, 'placement-card'); card.append(node('p', label, 'small'),node('p',value,'stat-value')); stats.append(card);
      }
    }
    const focus = $('home-focus'); focus.replaceChildren();
    resultList(focus, profile ? 'A useful focus' : 'Start with understanding', profile?.weak_topics.slice(0,3).map(t=>t.display_name) || [], profile ? 'Practice will help identify the areas worth revisiting. Your study estimate is a guide, not an official JLPT result.' : 'Placement adapts to your answers. Complete beginners can start directly with an introductory profile.');
    const recent = $('home-recent'); recent.replaceChildren();
    resultList(recent, 'Recent learning', activity.map(event=>`${readable(event.event_type)}${event.topic ? ': '+event.topic : ''} · ${dateLabel(event.created_at)}`), 'Your learning activity will appear here after you start.');
    $('home-content').hidden = false;
  } finally { if (sequence === homeRequest) $('home-loading').hidden = true; }
}
async function applyOnboardingGoal() {
  const goal = $('onboarding-goal-select').value;
  if (placementLearnerId) await api(`/api/learners/${placementLearnerId}/preferences`, jsonOptions('PATCH',{primary_goal:goal}));
  try { sessionStorage.removeItem('japanese-tutor-onboarding-goal'); } catch { /* Optional draft. */ }
}
document.querySelector('.skip-link').addEventListener('click', event => { event.preventDefault(); $('main-content').focus(); });
$('fresh-profile').addEventListener('click', () => {
  if (busy || assessmentBusy) return;
  try { localStorage.removeItem(resumeKey); } catch { /* Server records are kept. */ }
  assessmentState = null; pendingSubmission = null;
  $('placement-intro').hidden = false; $('placement-question').hidden = true; $('placement-result').hidden = true;
  $('onboarding-goal').hidden = false; $('onboarding-experience').hidden = true;
  remember('learner', null); placementLearnerId = null; sessionId = null; savedSession = false;
  document.dispatchEvent(new Event('learner-changed'));
  appReady = true; $('app-error').hidden = true; showPanel('placement');
});
$('home-action').addEventListener('click', () => {
  if (homeNext === 'placement') showPanel('placement');
  else { if (homeNext === 'review') $('study-focus').value = 'review'; showPanel('study'); }
});
$('onboarding-next').addEventListener('click', () => {
  $('onboarding-goal').hidden = true; $('onboarding-experience').hidden = false; visibleFocus('self-report');
  try { sessionStorage.setItem('japanese-tutor-onboarding-goal', $('onboarding-goal-select').value); } catch { /* Optional draft only. */ }
});
$('onboarding-back').addEventListener('click', () => { $('onboarding-experience').hidden = true; $('onboarding-goal').hidden = false; visibleFocus('onboarding-goal-select'); });
$('preferences-form').addEventListener('input', () => { settingsDirty = true; $('profile-notice').textContent = 'You have unsaved changes.'; });
$('settings-retry').addEventListener('click', () => loadSettings().catch(settingsError));
$('app-retry').addEventListener('click', () => { if (!appReady) boot(); else { $('app-error').hidden = true; renderRoute(); } });
window.addEventListener('hashchange', renderRoute);
function connectionState() { $('connection-notice').hidden = navigator.onLine; }
window.addEventListener('online', connectionState); window.addEventListener('offline', connectionState);
document.addEventListener('learner-changed', () => { ++homeRequest; settingsLearner = null; settingsDirty = false; });
async function boot() {
  if (booting) return;
  booting = true; $('app-error').hidden = true; $('app-loading').hidden = false;
  renderRoute();
  try {
    try { const goal = sessionStorage.getItem('japanese-tutor-onboarding-goal'); if (goal) $('onboarding-goal-select').value = goal; } catch { /* Optional draft only. */ }
    const id = recalled('learner');
    await Promise.all([id ? activateLearner(id) : Promise.resolve(), resumeAssessment()]);
    if (id) {
      try { if (!sessionStorage.getItem('japanese-tutor-onboarding-goal')) $('onboarding-goal-select').value = activeProfile.preferences.primary_goal; } catch { /* Optional draft. */ }
    }
    appReady = true;
  } catch (error) { showAppError(error); }
  finally { booting = false; $('app-loading').hidden = true; }
  if (appReady) await renderRoute();
}
connectionState();
boot();
