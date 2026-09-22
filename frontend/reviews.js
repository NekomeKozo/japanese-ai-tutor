'use strict';
let reviewRequest = 0;

async function refreshReviews() {
  const learner = placementLearnerId;
  const sequence = ++reviewRequest;
  $('daily-review').hidden = !learner;
  if (!learner) return;
  const minutes = Math.max(5, Math.min(60, Number($('review-minutes').value) || 10));
  const zone = Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
  try {
    const [queue, forecast] = await Promise.all([
      api(`/api/learners/${learner}/reviews/due?minutes=${minutes}`),
      api(`/api/learners/${learner}/reviews/forecast?timezone=${encodeURIComponent(zone)}`)
    ]);
    if (sequence !== reviewRequest || learner !== placementLearnerId) return;
    $('review-summary').textContent = queue.due_count ? `${queue.due_count} ready for review. We’ll start with ${queue.items.length} useful ${queue.items.length === 1 ? 'item' : 'items'}, about ${queue.selected_minutes} minutes.` : 'Nothing is ready for spaced review yet. Learn or practice something in Today’s Study.';
    if (queue.backlog) $('review-summary').textContent += ' You can work through the rest over later sessions.';
    $('review-counts').textContent = `Vocabulary ${queue.counts.vocabulary} · Grammar ${queue.counts.grammar} · Kanji ${queue.counts.kanji}`;
    $('review-forecast').textContent = `Ready or coming up today: ${forecast.today} · Tomorrow: ${forecast.tomorrow}. Dates use ${zone}.`;
    const active = studyPlan && ['planned', 'in_progress'].includes(studyPlan.status);
    $('review-start').textContent = active ? 'Continue saved session' : 'Start review';
    $('review-start').disabled = !active && !queue.items.length;
  } catch (error) {
    if (sequence === reviewRequest) $('review-summary').textContent = error.message;
  }
}

$('review-minutes').addEventListener('change', refreshReviews);
document.addEventListener('learner-changed', () => { ++reviewRequest; $('daily-review').hidden = true; });
$('review-start').addEventListener('click', () => studyAction(async () => {
  if (!studyPlan || !['planned', 'in_progress'].includes(studyPlan.status)) {
    const minutes = Number($('review-minutes').value);
    if (!Number.isInteger(minutes) || minutes < 5 || minutes > 60) throw new Error('Choose 5–60 whole minutes.');
    studyPlan = await api('/api/curriculum/plan', jsonOptions('POST', {learner_id: placementLearnerId, available_minutes: minutes, session_type: 'review'}));
    remember(`study-${placementLearnerId}`, studyPlan.session_id);
  }
  if (studyPlan.status === 'planned') studyPlan = await api(`${studyPath()}/start`, {method:'POST'});
  renderStudy(); await currentActivity(); await refreshReviews();
}));
