'use strict';

let assessmentState = null;
let assessmentBusy = false;
let pendingSubmission = null;
const resumeKey = 'japanese-tutor-assessment-v1';

function readResume() { try { return localStorage.getItem(resumeKey); } catch { return null; } }
function saveResume(id) { try { localStorage.setItem(resumeKey, id); } catch { /* Assessment works without browser storage. */ } }

function showPanel(which) {
  $('placement-panel').hidden = which !== 'placement';
  $('tutor-panel').hidden = which !== 'tutor';
  $('profile-panel').hidden = which !== 'profile';
  $('study-panel').hidden = which !== 'study';
  $('study-tab').setAttribute('aria-current', which === 'study' ? 'page' : 'false');
  $('profile-tab').setAttribute('aria-current', which === 'profile' ? 'page' : 'false');
  $('reset').hidden = which !== 'tutor';
  $('placement-tab').setAttribute('aria-current', which === 'placement' ? 'page' : 'false');
  $('tutor-tab').setAttribute('aria-current', which === 'tutor' ? 'page' : 'false');
  if (which === 'tutor') $('message').focus();
}

function assessmentSetBusy(value) {
  assessmentBusy = value;
  for (const id of ['start-assessment', 'submit-answer', 'dont-know', 'self-report', 'assessment-answer', 'question-choices', 'retry-assessment', 'retake-assessment']) $(id).disabled = value;
  $('submit-answer').textContent = value ? 'Checking your answer…' : 'Submit answer';
}

function assessmentError(error) {
  $('assessment-error').textContent = error instanceof TypeError ? 'Cannot reach the server. Your saved assessment is safe; reload it when the connection returns.' : error.message;
  $('assessment-error').hidden = false;
  $('retry-assessment').hidden = !readResume();
  $('retake-assessment').hidden = false;
}

function resultList(container, title, items, empty) {
  container.append(node('h3', title));
  if (!items.length) { container.append(node('p', empty)); return; }
  const list = node('ul');
  items.forEach((item) => list.append(node('li', item)));
  container.append(list);
}

async function beginPlacedLearning(profile) {
  if (busy) return;
  setBusy(true);
  try { await activateLearner(profile.learner_id); showPanel('tutor'); }
  catch (error) { assessmentError(error); }
  finally { setBusy(false); }
}

function renderAssessmentResult(profile) {
  const container = $('placement-result');
  container.replaceChildren();
  const heading = node('h2', 'Placement assessment complete');
  heading.tabIndex = -1;
  container.append(heading, node('p', 'Estimated current level', 'eyebrow'), node('h3', profile.overall_estimate),
    node('p', `Probable study range: ${profile.probable_study_range}`),
    node('p', `Confidence: ${profile.confidence_label} · ${profile.questions_answered} questions answered.`));
  const table = node('table');
  const caption = node('caption', 'Skill profile — estimates from sampled items');
  const head = node('thead');
  const headRow = node('tr');
  ['Skill', 'Estimate', 'Evidence'].forEach((label) => { const th = node('th', label); th.scope = 'col'; headRow.append(th); });
  head.append(headRow);
  table.append(caption, head);
  const body = node('tbody');
  Object.entries(profile.skills).forEach(([name, skill]) => {
    const row = node('tr');
    const label = node('th', name.replaceAll('_', ' ')); label.scope = 'row';
    row.append(label, node('td', skill.estimated_level), node('td', `${skill.evidence_count} scored${skill.evidence_count < 2 ? ' · limited' : ''}${skill.unavailable_count ? ` · ${skill.unavailable_count} unavailable` : ''}`));
    body.append(row);
  });
  table.append(body);
  const scroll = node('div', undefined, 'table-scroll'); scroll.append(table); container.append(scroll);
  resultList(container, 'Strong areas in this sample', profile.strong_topics, 'Not enough repeated evidence to identify strengths yet.');
  resultList(container, 'Needs attention', profile.weak_topics, 'No repeated weak topic was identified in this sample.');
  container.append(node('h3', 'Recommended starting point'), node('p', profile.recommended_starting_point));
  resultList(container, 'About this estimate', profile.limitations, '');
  const begin = node('button', 'Begin learning'); begin.type = 'button';
  begin.addEventListener('click', () => beginPlacedLearning(profile));
  container.append(begin);
  heading.focus();
}

function renderAssessment(state) {
  assessmentState = state;
  saveResume(state.assessment_id);
  $('placement-intro').hidden = true;
  $('placement-question').hidden = state.status !== 'in_progress';
  $('placement-result').hidden = state.status !== 'completed';
  $('retake-assessment').hidden = false;
  $('retry-assessment').hidden = true;
  if (state.status === 'completed') { renderAssessmentResult(state.result); return; }
  const question = state.question;
  $('question-heading').textContent = `Question ${state.question_number} · ${question.skill.replaceAll('_', ' ')}`;
  $('assessment-progress').textContent = `${state.questions_answered} answered · Up to ${state.maximum_questions} questions. The length adapts to your answers.`;
  $('assessment-meter').value = state.questions_answered;
  $('question-prompt').textContent = question.prompt;
  const choices = $('question-choices');
  choices.replaceChildren(node('legend', 'Choose your answer'));
  choices.hidden = !question.choices.length;
  question.choices.forEach((text, index) => {
    const label = node('label', undefined, 'choice');
    const radio = node('input'); radio.type = 'radio'; radio.name = 'placement-choice'; radio.value = text;
    radio.id = `placement-choice-${index}`;
    label.append(radio, node('span', text)); choices.append(label);
  });
  $('assessment-answer').value = '';
  $('assessment-answer').hidden = Boolean(question.choices.length);
  $('answer-label').hidden = Boolean(question.choices.length);
  $('question-heading').focus();
}

async function startAssessment() {
  if (assessmentBusy) return;
  assessmentSetBusy(true);
  $('assessment-error').hidden = true;
  $('assessment-notice').hidden = true;
  try {
    const state = await api('/api/assessments', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({self_report: $('self-report').value}) });
    pendingSubmission = null;
    renderAssessment(state);
  } catch (error) { assessmentError(error); }
  finally { assessmentSetBusy(false); }
}

async function resumeAssessment() {
  const id = readResume();
  if (!id || assessmentBusy) return;
  assessmentSetBusy(true);
  $('assessment-error').hidden = true;
  try { renderAssessment(await api(`/api/assessments/${encodeURIComponent(id)}`)); pendingSubmission = null; }
  catch (error) { assessmentError(error); }
  finally { assessmentSetBusy(false); }
}

async function submitAssessment(dontKnow) {
  if (assessmentBusy || !assessmentState?.question) return;
  const question = assessmentState.question;
  const answer = dontKnow ? null : question.choices.length
    ? document.querySelector('input[name="placement-choice"]:checked')?.value : $('assessment-answer').value.trim();
  if (!dontKnow && !answer) { assessmentError(new Error('Choose or enter an answer, or select I don’t know.')); return; }
  const payload = {question_id: question.id, answer, dont_know: dontKnow};
  const signature = JSON.stringify(payload);
  if (!pendingSubmission || pendingSubmission.signature !== signature) pendingSubmission = {signature, id: crypto.randomUUID()};
  payload.submission_id = pendingSubmission.id;
  assessmentSetBusy(true);
  $('assessment-error').hidden = true;
  $('assessment-notice').hidden = true;
  try {
    const state = await api(`/api/assessments/${assessmentState.assessment_id}/answers`, {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(payload)});
    pendingSubmission = null;
    renderAssessment(state);
    if (state.notice) { $('assessment-notice').textContent = state.notice; $('assessment-notice').hidden = false; }
  } catch (error) { assessmentError(error); }
  finally { assessmentSetBusy(false); }
}

$('placement-tab').addEventListener('click', () => showPanel('placement'));
$('tutor-tab').addEventListener('click', () => showPanel('tutor'));
$('skip-placement').addEventListener('click', async () => {
  if (busy) return;
  setBusy(true);
  try { const learner = await api('/api/learners', {method: 'POST'}); await activateLearner(learner.learner_id); showPanel('tutor'); }
  catch (error) { assessmentError(error); }
  finally { setBusy(false); }
});
$('start-assessment').addEventListener('click', startAssessment);
$('assessment-form').addEventListener('submit', (event) => { event.preventDefault(); submitAssessment(false); });
$('dont-know').addEventListener('click', () => submitAssessment(true));
$('retry-assessment').addEventListener('click', resumeAssessment);
$('retake-assessment').addEventListener('click', () => {
  $('placement-intro').hidden = false; $('placement-question').hidden = true; $('placement-result').hidden = true;
  $('assessment-error').hidden = true; $('assessment-notice').hidden = true;
  $('retake-assessment').hidden = true; $('retry-assessment').hidden = !readResume();
});
showPanel('placement');
resumeAssessment();
