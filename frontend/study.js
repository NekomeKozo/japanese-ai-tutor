'use strict';

let studyPlan = null;
let studyActivity = null;
let studyPending = null;
let studyBusy = false;
const studyPath = () => `/api/learners/${placementLearnerId}/study/${studyPlan.session_id}`;

function studyError(error) { $('study-error').textContent = friendlyError(error); $('study-error').hidden = false; $('study-retry').hidden = Boolean(studyPlan); }
async function studyAction(action) {
  if (busy || studyBusy) return;
  studyBusy = true; setBusy(true); $('study-error').hidden = true; $('study-retry').hidden = true;
  const buttons = $('study-panel').querySelectorAll('button,input,select,textarea'); buttons.forEach(button => { button.disabled = true; });
  const trigger = document.activeElement?.id;
  $('study-status').textContent = trigger === 'study-generate' ? 'Building your study plan…' : trigger === 'study-submit' ? 'Checking your answer…' : 'Preparing your next study step…';
  try { await action(); $('study-status').textContent = 'Saved · You can return to this plan later.'; }
  catch (error) {
    studyError(error); $('study-status').textContent = 'This step couldn’t finish. Your answer stays here; try again when ready.';
    if ($('study-content').textContent === 'Preparing this activity…') $('study-content').replaceChildren(node('p', 'Lesson unavailable. Choose Continue session to retry, or skip this activity.'));
  }
  finally { studyBusy = false; setBusy(false); buttons.forEach(button => { button.disabled = false; }); await refreshReviews(); }
}

function renderStudy() {
  const hasLearner = Boolean(placementLearnerId);
  $('study-panel').setAttribute('data-state', studyPlan?.status || 'setup');
  const active = studyPlan && ['planned', 'in_progress'].includes(studyPlan.status);
  $('study-create-learner').hidden = hasLearner;
  $('study-plan-form').hidden = !hasLearner || active;
  $('study-intro').textContent = active ? 'Your plan is saved. Work through one activity at a time.' : hasLearner ? 'Choose a study length and focus. Your saved evidence guides the plan.' : 'Complete placement for a tailored starting point, or begin with a simple introductory profile.';
  $('study-preview').hidden = !studyPlan;
  $('study-controls').hidden = !active;
  $('daily-review').hidden = !hasLearner || active;
  if (!studyPlan) { $('study-activity').hidden = true; return; }
  const done = studyPlan.activities.filter(a => ['completed','skipped'].includes(a.status)).length;
  $('study-meter').max = Math.max(1, studyPlan.activities.length); $('study-meter').value = done;
  $('study-progress-label').textContent = `${done} of ${studyPlan.activities.length} activities finished`;
  const preview = $('study-preview'); preview.replaceChildren(node('h2', studyPlan.status === 'completed' ? 'Session recap' : 'Your study plan'));
  preview.append(node('p', `Planned time: ${studyPlan.estimated_minutes} minutes · ${studyPlan.status.replaceAll('_', ' ')}`), node('p', studyPlan.note, 'small'));
  const list = node('ol');
  studyPlan.activities.forEach(activity => {
    const item = node('li'); item.append(node('strong', `${activity.title} · ${activity.duration_minutes} min`),
      node('p', `${activity.purpose === 'review' ? 'Review' : 'New material'} · ${activity.status.replaceAll('_', ' ')} · ${activity.reason}`, 'small'));
    list.append(item);
  });
  if (studyPlan.status === 'in_progress') { const details = node('details'); details.append(node('summary', 'See your plan'), list); preview.append(details); } else preview.append(list);
  $('study-start').textContent = studyPlan.status === 'planned' ? 'Start session' : studyPlan.current_activity_id ? 'Continue session' : 'Finish session';
  if (studyPlan.recap) {
    const completed = studyPlan.activities.filter(a => a.status === 'completed');
    preview.append(node('p', `${completed.length} activities completed · ${completed.filter(a => a.purpose === 'review').length} reviews completed`));
    resultList(preview, 'Practiced', studyPlan.recap.practiced, 'No activities were completed.');
    resultList(preview, 'Went well in this session', studyPlan.recap.strong_performance, 'More evidence is needed.');
    resultList(preview, 'Worth revisiting', studyPlan.recap.needs_review, 'No repeated review need established by this session.');
    preview.append(node('p', `${studyPlan.recap.skipped_count} skipped · ${studyPlan.recap.note}`, 'small'));
    const home = node('a', 'Return Home', 'button-link'); home.href = '#home'; preview.append(home);
    $('study-activity').hidden = true;
  }
}

async function loadStudy() {
  if (!placementLearnerId) { studyPlan = null; renderStudy(); return; }
  if (studyPlan) { renderStudy(); await refreshReviews(); return; }
  $('study-error').hidden = true; $('study-retry').hidden = true;
  $('study-status').textContent = 'Loading your saved study…';
  $('study-plan-form').hidden = true;
  const learner = placementLearnerId;
  const active = await api(`/api/learners/${learner}/study/active`);
  if (learner !== placementLearnerId) return;
  let saved = active;
  if (!active) {
    const last = recalled(`study-${learner}`);
    if (last) {
      try { saved = await api(`/api/learners/${learner}/study/${last}`); }
      catch (error) { if (error.code !== 'study_not_found') throw error; }
    }
  }
  if (learner !== placementLearnerId) return;
  studyPlan = saved;
  if (studyPlan) remember(`study-${learner}`, studyPlan.session_id);
  studyActivity = null; $('study-activity').hidden = true; renderStudy(); $('study-status').textContent = ''; await refreshReviews();
}

async function currentActivity() {
  studyPlan = await api(studyPath());
  renderStudy();
  if (!studyPlan.current_activity_id) {
    studyPlan = await api(`${studyPath()}/complete`, {method:'POST'}); renderStudy(); visibleFocus('study-preview'); return;
  }
  studyActivity = studyPlan.activities.find(activity => activity.activity_id === studyPlan.current_activity_id);
  $('study-activity').hidden = false;
  const reviewItems = studyPlan.activities.filter(a => a.review_schedule_id);
  const reviewPosition = reviewItems.findIndex(a => a.activity_id === studyActivity.activity_id) + 1;
  $('study-heading').textContent = studyActivity.review_schedule_id ? `Review ${reviewPosition} of ${reviewItems.length} · ${studyActivity.title} · ${studyActivity.focus_dimension.replaceAll('_', ' ')}` : `${studyActivity.order}. ${studyActivity.title}`;
  $('study-purpose').textContent = `${studyActivity.purpose === 'review' ? 'Review' : 'Learn & practice'} · ${studyActivity.duration_minutes} minute estimate · ${studyActivity.reason}`;
  $('study-content').replaceChildren(node('p', 'Preparing this activity…'));
  $('study-feedback').textContent = '';
  $('study-answer-form').hidden = true; $('study-next').hidden = true; $('study-skip').hidden = false;
  const opened = await api(`${studyPath()}/activities/${studyActivity.activity_id}/open`, {method:'POST'});
  $('study-content').replaceChildren();
  renderReply({...opened.response, exercise: {...opened.response.exercise, choices:[]}}, $('study-content'));
  const choices = opened.response.exercise.choices;
  const fieldset = $('study-choices'); fieldset.replaceChildren(node('legend', 'Choose an answer')); fieldset.hidden = !choices.length;
  choices.forEach(text => {
    const label = node('label', undefined, 'choice'); const radio = node('input'); radio.type = 'radio'; radio.name = 'study-choice'; radio.value = text;
    label.append(radio, node('span', text)); fieldset.append(label);
  });
  $('study-answer').value = ''; $('study-answer').hidden = Boolean(choices.length); $('study-answer-label').hidden = Boolean(choices.length);
  $('study-answer-form').hidden = false; studyPending = null;
  studyPlan = await api(studyPath()); renderStudy(); visibleFocus('study-heading');
}

document.addEventListener('learner-changed', () => { studyPlan = null; studyActivity = null; studyPending = null; $('study-error').hidden = true; $('study-retry').hidden = true; $('study-status').textContent = ''; renderStudy(); });
$('study-create-learner').addEventListener('click', () => studyAction(async () => {
  const learner = await api('/api/learners', {method:'POST'}); await activateLearner(learner.learner_id); renderStudy();
}));
$('study-plan-form').addEventListener('submit', event => {
  event.preventDefault(); studyAction(async () => {
    studyPlan = await api('/api/curriculum/plan', jsonOptions('POST', {learner_id: placementLearnerId,
      available_minutes:Number($('study-minutes').value), session_type:$('study-focus').value}));
    remember(`study-${placementLearnerId}`, studyPlan.session_id); renderStudy();
  });
});
$('study-start').addEventListener('click', () => studyAction(async () => {
  if (studyActivity && !$('study-activity').hidden && !$('study-answer-form').hidden) { visibleFocus('study-heading'); return; }
  if (studyPlan.status === 'planned') studyPlan = await api(`${studyPath()}/start`, {method:'POST'});
  await currentActivity();
}));
$('study-answer-form').addEventListener('submit', event => {
  event.preventDefault(); studyAction(async () => {
    const answer = $('study-choices').hidden ? $('study-answer').value.trim() : document.querySelector('input[name="study-choice"]:checked')?.value;
    if (!answer) throw new Error('Enter or choose an answer, or skip this activity.');
    const signature = `${studyActivity.activity_id}:${answer}`;
    if (!studyPending || studyPending.signature !== signature) studyPending = {signature, id:crypto.randomUUID()};
    const result = await api(`${studyPath()}/activities/${studyActivity.activity_id}/complete`, jsonOptions('POST', {submission_id:studyPending.id, answer}));
    $('study-feedback').textContent = `${result.score >= .8 ? 'Well done.' : result.score >= .5 ? 'Partly correct.' : 'Keep practicing.'} ${result.feedback} Reference: ${result.reference_answers.join(' / ')}`;
    if (result.next_review) $('study-feedback').textContent += ` Next review: ${dateLabel(result.next_review)}.`;
    $('study-answer-form').hidden = true; $('study-skip').hidden = true; $('study-next').hidden = false;
    studyPlan = await api(studyPath()); renderStudy(); studyPending = null; await refreshReviews();
  });
});
$('study-next').addEventListener('click', () => studyAction(currentActivity));
$('study-skip').addEventListener('click', () => studyAction(async () => {
  await api(`${studyPath()}/activities/${studyActivity.activity_id}/skip`, {method:'POST'}); await currentActivity();
}));
$('study-abandon').addEventListener('click', () => studyAction(async () => {
  studyPlan = await api(`${studyPath()}/abandon`, {method:'POST'}); $('study-activity').hidden = true; renderStudy();
}));

$('study-retry').addEventListener('click', () => loadStudy().catch(studyError));
