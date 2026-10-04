'use strict';

const $ = (id) => document.getElementById(id);
let sessionId = null;
let busy = false;
let placementLearnerId = null;
let savedSession = false;
let pendingChat = null;
const welcome = $('conversation').firstElementChild.cloneNode(true);
function appendTutorWelcome() {
  const article = welcome.cloneNode(true); $('conversation').append(article);
  attachJapaneseAudio(article, 'こんにちは！', 'tutor greeting');
}
attachJapaneseAudio($('conversation').firstElementChild, 'こんにちは！', 'tutor greeting');

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function setBusy(value) {
  busy = value;
  for (const id of ['send', 'reset', 'message', 'mode', 'level']) $(id).disabled = value;
  $('send').textContent = value ? 'Working…' : 'Send message';
  $('conversation').setAttribute('aria-busy', String(value));
  practiceControls();
  if (!value && tutorOpenPending) {
    tutorOpenPending = false;
    if (!$('tutor-panel').hidden) ensureTutorSession();
  }
}

function friendlyError(error) {
  if (error instanceof TypeError || error instanceof SyntaxError) return 'We couldn’t connect just now. Check your connection and try again.';
  if (['provider_error','provider_unavailable','provider_not_configured','invalid_provider_response'].includes(error.code) || /provider|API key|model configuration/i.test(error.message)) return 'The tutor couldn’t answer just now. Your text is still here; please try again shortly.';
  return error.message || 'Something went wrong. Please try again.';
}
const pendingAPIReads = new Map();
let apiReadGeneration = 0;
function invalidateAPIReads() { ++apiReadGeneration; pendingAPIReads.clear(); }
document.addEventListener('learner-changed',invalidateAPIReads);
document.addEventListener('learning-updated',invalidateAPIReads);
async function api(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase();
  // Share only equivalent in-flight reads. No settled responses or private data
  // survive navigation via a shared/persistent cache; caller-specific options bypass.
  if (method !== 'GET') { invalidateAPIReads(); return requestAPI(path,options); }
  if (Object.keys(options).some(key => key !== 'method')) return requestAPI(path,options);
  const key = `${apiReadGeneration}:${placementLearnerId || ''}:${path}`;
  const existing = pendingAPIReads.get(key);
  if (existing) return existing.then(data => JSON.parse(JSON.stringify(data)));
  const request = requestAPI(path,options).finally(() => { if (pendingAPIReads.get(key) === request) pendingAPIReads.delete(key); });
  pendingAPIReads.set(key,request);
  return request.then(data => JSON.parse(JSON.stringify(data)));
}
async function requestAPI(path, options = {}) {
  const response = await fetch(path, options);
  if (response.status === 401 && path !== '/api/access') {
    window.location.assign('/access');
    throw new Error('Sign in to continue.');
  }
  if (response.status === 204) return null;
  const data = await response.json();
  if (!response.ok) {
    const error = new Error(data.error?.message || 'The request failed. Please try again.');
    error.code = data.error?.code;
    throw error;
  }
  if (options.method && options.method !== 'GET') document.dispatchEvent(new Event('learning-updated'));
  return data;
}

function showError(error) {
  $('error').textContent = friendlyError(error);
  $('error').hidden = false;
}

function addMessage(who, text, container = $('conversation')) {
  const article = node('article', undefined, `message ${who}`);
  article.append(node('p', who === 'learner' ? 'YOU' : 'TUTOR', 'speaker'), node('p', text));
  container.append(article);
  if (who === 'tutor') attachJapaneseAudio(article, text, 'tutor reply');
  return article;
}

function renderReply(reply, container = $('conversation')) {
  const article = addMessage('tutor', reply.message, container);
  if (reply.evaluation) article.append(node('p', reply.evaluation.status.replaceAll('_', ' '), 'evaluation'));
  if (reply.correction) {
    article.append(node('h2', 'Your sentence'), node('p', reply.correction.original, 'correction-original'), node('h2', 'Suggested Japanese'), node('p', reply.correction.improved, 'correction-improved'));
    attachJapaneseAudio(article, reply.correction.improved, 'suggested Japanese');
  }
  if (reply.explanation) article.append(node('h2', reply.correction ? 'Why' : 'Explanation'), node('p', reply.explanation));
  if (reply.examples.length) {
    const list = node('ul');
    reply.examples.forEach((example) => list.append(node('li', example)));
    article.append(node('h2', 'Examples'), list);
    attachJapaneseAudio(article, reply.examples.join('\n'), 'Japanese examples');
  }
  if (reply.exercise) {
    article.append(node('h2', 'Your turn'), node('p', reply.exercise.question));
    const list = node('ol');
    reply.exercise.choices.forEach((choice) => list.append(node('li', choice)));
    if (list.childElementCount) article.append(list);
    if (reply.exercise.hint) {
      const hint = node('details');
      hint.append(node('summary', 'Show hint'), node('p', reply.exercise.hint));
      article.append(hint);
    }
  }
}

async function refreshStatus() {
  const health = await api('/api/health');
  $('status').textContent = health.provider_configured
    ? 'Ready when you are. Ask a question or try some Japanese.' : 'The tutor is unavailable right now. Please try again later.';
}

async function resetSession() {
  if (practiceState?.status === 'active') { showError(new Error('Finish your active conversation first.')); return; }
  japaneseAudio.stop();
  clearVoiceReply();
  setBusy(true);
  $('error').hidden = true;
  try {
    if (sessionId) {
      try { await api(savedSession ? `/api/learners/${placementLearnerId}/sessions/${sessionId}/close` : `/api/sessions/${sessionId}`, { method: savedSession ? 'POST' : 'DELETE' }); }
      catch (error) { if (error.code !== 'session_expired') throw error; }
      sessionId = null;
    }
    const session = await api(placementLearnerId ? `/api/learners/${placementLearnerId}/sessions` : '/api/sessions', { method: 'POST' });
    sessionId = session.session_id;
    savedSession = Boolean(placementLearnerId);
    pendingChat = null;
    applyPractice(null);
    if (savedSession) remember(`session-${placementLearnerId}`, sessionId);
    $('conversation').replaceChildren(); appendTutorWelcome();
    $('message').value = '';
    $('mode').value = 'chat';
    updateCount();
    await refreshStatus();
  } catch (error) { showError(error); }
  finally { setBusy(false); visibleFocus('message'); }
}

function updateCount() { $('count').textContent = `${$('message').value.length} / 4,000 · Ctrl+Enter to send`; }

async function submitChatMessage() {
  if (busy) return;
  const message = $('message').value.trim();
  if (!message) { showError(new Error('Enter a message or topic first.')); return; }
  if (!sessionId) { showError(new Error('Start a new session to connect to the tutor.')); return; }
  japaneseAudio.stop();
  if(['requesting','recording','processing'].includes(browserRecorder.state().phase)) clearVoiceReply();
  setBusy(true);
  $('error').hidden = true;
  $('status').textContent = 'The tutor is thinking…';
  try {
    const payload = { session_id: sessionId, message, mode: $('mode').value, level: $('level').value, learner_id: placementLearnerId };
    const transcription=voiceTranscriptionFor(message);
    if(transcription)payload.transcription_id=transcription;
    const signature = JSON.stringify(payload);
    if (!pendingChat || pendingChat.signature !== signature) pendingChat = { signature, id: crypto.randomUUID() };
    if (savedSession) payload.request_id = pendingChat.id;
    const data = await api('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload) });
    if (sessionId !== payload.session_id || placementLearnerId !== payload.learner_id) return false;
    pendingChat = null;
    addMessage('learner', message);
    renderReply(data.response);
    $('message').value = '';
    if (data.response.exercise) $('mode').value = 'chat';
    updateCount();
    $('conversation').scrollTop = $('conversation').scrollHeight;
    $('status').textContent = 'Your turn · Take your time.';
    voiceChatSucceeded();
    await refreshPractice();
    return true;
  } catch (error) {
    showError(error);
    $('status').textContent = 'Your message is still in the editor. Retry, or start a new session if it expired.';
    return false;
  } finally { setBusy(false); visibleFocus('message'); }
}
$('chat-form').addEventListener('submit', async event => { event.preventDefault(); return submitChatMessage(); });
$('reset').addEventListener('click', resetSession);
$('message').addEventListener('input', updateCount);
$('message').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !event.isComposing) {
    event.preventDefault(); $('chat-form').requestSubmit();
  }
});
