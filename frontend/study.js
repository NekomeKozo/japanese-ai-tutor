'use strict';

let studyPlan = null;
let studyActivity = null;
let studyPending = null;
let studyBusy = false;
const studyPath = () => `/api/learners/${placementLearnerId}/study/${studyPlan.session_id}`;

function studyError(error) { $('study-error').textContent = error.message; $('study-error').hidden = false; }
async function studyAction(action) {
  if (busy || studyBusy) return;
  studyBusy = true; setBusy(true); $('study-error').hidden = true;
  const buttons = $('study-panel').querySelectorAll('button'); buttons.forEach(button => { button.disabled = true; });
  $('study-status').textContent = 'Working on your study session…';
  try { await action(); $('study-status').textContent = 'Saved · You can return to this plan later.'; }
  catch (error) {
    studyError(error); $('study-status').textContent = 'Your saved plan is safe. Retry or skip this activity.';
    if ($('study-content').textContent === 'Preparing this activity…') $('study-content').replaceChildren(node('p', 'Lesson unavailable. Choose Continue session to retry, or skip this activity.'));
  }
  finally { studyBusy = false; setBusy(false); buttons.forEach(button => { button.disabled = false; }); await refreshReviews(); }
}

function renderStudy() {
  const hasLearner = Boolean(placementLearnerId);
  const active = studyPlan && ['planned', 'in_progress'].includes(studyPlan.status);
  $('study-create-learner').hidden = hasLearner;
  $('study-plan-form').hidden = !hasLearner || active;
  $('study-intro').textContent = hasLearner ? 'Choose a study length and focus. Your saved evidence guides the plan.' : 'Complete placement for a tailored starting point, or begin with a simple introductory profile.';
  $('study-preview').hidden = !studyPlan;
  $('study-controls').hidden = !active;
  if (!studyPlan) { $('study-activity').hidden = true; return; }
  const preview = $('study-preview'); preview.replaceChildren(node('h2', studyPlan.status === 'completed' ? 'Session recap' : 'Your study plan'));
  preview.append(node('p', `${studyPlan.estimated_minutes} minutes · ${studyPlan.status.replaceAll('_', ' ')}`), node('p', studyPlan.note, 'small'));
  const list = node('ol');
  studyPlan.activities.forEach(activity => {
    const item = node('li'); item.append(node('strong', `${activity.title} · ${activity.duration_minutes} min`),
      node('p', `${activity.purpose === 'review' ? 'Review' : 'New material'} · ${activity.status.replaceAll('_', ' ')} · ${activity.reason}`, 'small'));
    list.append(item);
  }); preview.append(list);
  $('study-start').textContent = studyPlan.status === 'planned' ? 'Start session' : studyPlan.current_activity_id ? 'Continue session' : 'Finish session';
  if (studyPlan.recap) {
    resultList(preview, 'Practiced', studyPlan.recap.practiced, 'No activities were completed.');
    resultList(preview, 'Went well in this session', studyPlan.recap.strong_performance, 'More evidence is needed.');
    resultList(preview, 'Worth revisiting', studyPlan.recap.needs_review, 'No repeated review need established by this session.');
    preview.append(node('p', `${studyPlan.recap.skipped_count} skipped · ${studyPlan.recap.note}`, 'small'));
    $('study-activity').hidden = true;
  }
}

async function loadStudy() {
  $('study-error').hidden = true;
  if (!placementLearnerId) { studyPlan = null; renderStudy(); return; }
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
  studyActivity = null; $('study-activity').hidden = true; renderStudy(); await refreshReviews();
}

async function currentActivity() {
  studyPlan = await api(studyPath());
  renderStudy();
  if (!studyPlan.current_activity_id) {
    studyPlan = await api(`${studyPath()}/complete`, {method:'POST'}); renderStudy(); return;
  }
  studyActivity = studyPlan.activities.find(activity => activity.activity_id === studyPlan.current_activity_id);
  $('study-activity').hidden = false;
  const reviewItems = studyPlan.activities.filter(a => a.review_schedule_id);
  const reviewPosition = reviewItems.findIndex(a => a.activity_id === studyActivity.activity_id) + 1;
  $('study-heading').textContent = studyActivity.review_schedule_id ? `Review ${reviewPosition} of ${reviewItems.length} · ${studyActivity.title} · ${studyActivity.focus_dimension.replaceAll('_', ' ')}` : `${studyActivity.order}. ${studyActivity.title}`;
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
  studyPlan = await api(studyPath()); renderStudy(); $('study-heading').focus();
}

$('study-tab').addEventListener('click', () => { showPanel('study'); loadStudy().catch(studyError); });
document.addEventListener('learner-changed', () => { studyPlan = null; studyActivity = null; studyPending = null; renderStudy(); });
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
