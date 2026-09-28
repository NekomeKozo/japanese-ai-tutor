'use strict';

let masteryOffset = 0;
let masteryRequest = 0;
const masteryLabels = {new:'Not yet assessed', learning:'Learning', developing:'Developing', familiar:'Familiar', strong:'Strong', needs_review:'Needs review'};
const confidenceLabel = value => value < .35 ? 'Limited evidence' : value < .65 ? 'Moderate confidence' : 'High confidence';

async function showMasteryTopic(id, learner) {
  const sequence = ++masteryRequest;
  $('mastery-detail').replaceChildren(node('p', 'Loading topic details…'));
  try {
    const item = await api(`/api/learners/${learner}/mastery/${encodeURIComponent(id)}`);
    if (learner !== placementLearnerId || sequence !== masteryRequest) return;
    const detail = $('mastery-detail'); detail.replaceChildren(node('h3', item.display_name));
    detail.append(node('p', `${masteryLabels[item.status]} · ${confidenceLabel(item.confidence)}`));
    if (item.meaning) detail.append(node('p', `${item.meaning}${item.reading ? ' · ' + item.reading : ''}`));
    const list = node('dl', undefined, 'mastery-dimensions');
    Object.entries(item.dimensions).forEach(([name, value]) => {
      list.append(node('dt', name.replaceAll('_', ' ')), node('dd', value.score === null ? 'Not enough evidence' : `${masteryLabels[value.status]} · ${confidenceLabel(value.confidence)}`));
    });
    detail.append(list, node('p', `${item.evidence_count} assessed encounters · ${item.independent_count} distinct question contexts`),
      node('p', `Last practiced: ${dateLabel(item.last_seen_at)}`));
    if (item.reading_contexts.length) detail.append(node('p', `Readings tested in: ${item.reading_contexts.join(', ')}. Other readings may still be unknown.`));
    if (item.history.length) {
      const history = node('details'); history.append(node('summary', 'Recent knowledge changes'));
      item.history.slice(0, 8).forEach(entry => history.append(node('p', `${dateLabel(entry.recorded_at)} · ${masteryLabels[entry.status]} · ${confidenceLabel(entry.confidence)}`)));
      detail.append(history);
    }
    detail.tabIndex = -1;
    detail.append(node('p', 'These are provisional learning estimates, not an official proficiency measurement.', 'small'));
    visibleFocus('mastery-detail');
  } catch (error) { if (sequence === masteryRequest) $('mastery-notice').textContent = friendlyError(error); }
}

async function renderMastery() {
  const learner = placementLearnerId;
  const sequence = ++masteryRequest;
  $('mastery-detail').replaceChildren();
  if (!learner) { $('mastery-list').replaceChildren(); return; }
  $('mastery-notice').textContent = 'Loading knowledge…';
  $('mastery-prev').disabled = true; $('mastery-next').disabled = true;
  const query = new URLSearchParams({limit:'20', offset:String(masteryOffset)});
  if ($('mastery-type').value) query.set('type', $('mastery-type').value);
  if ($('mastery-status').value) query.set('status', $('mastery-status').value);
  try {
    const data = await api(`/api/learners/${learner}/mastery?${query}`);
    if (learner !== placementLearnerId || sequence !== masteryRequest) return;
    const list = $('mastery-list'); list.replaceChildren();
    data.items.forEach(item => {
      const row = node('div', undefined, 'mastery-row');
      const button = node('button', item.display_name, 'secondary'); button.type = 'button';
      button.addEventListener('click', () => showMasteryTopic(item.topic_id, learner));
      row.append(button, node('span', `${masteryLabels[item.status]} · ${confidenceLabel(item.confidence)}`)); list.append(row);
    });
    $('mastery-notice').textContent = data.total ? `${masteryOffset + 1}–${masteryOffset + data.items.length} of ${data.total} topics. Select a topic to see its dimensions.` : 'No topics match these filters.';
    $('mastery-prev').disabled = masteryOffset === 0;
    $('mastery-next').disabled = masteryOffset + data.items.length >= data.total;
  } catch (error) { if (sequence === masteryRequest) $('mastery-notice').textContent = friendlyError(error); }
}

for (const id of ['mastery-type', 'mastery-status']) $(id).addEventListener('change', () => { masteryOffset = 0; renderMastery(); });
$('mastery-prev').addEventListener('click', () => { masteryOffset = Math.max(0, masteryOffset - 20); renderMastery(); });
$('mastery-next').addEventListener('click', () => { masteryOffset += 20; renderMastery(); });
document.addEventListener('learner-changed', () => { masteryOffset = 0; ++masteryRequest; $('mastery-list').replaceChildren(); $('mastery-detail').replaceChildren(); });
