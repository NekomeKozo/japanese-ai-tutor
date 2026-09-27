'use strict';

const $ = (id) => document.getElementById(id);
let sessionId = null;
let busy = false;
let placementLearnerId = null;
let savedSession = false;
let pendingChat = null;
const welcome = $('conversation').firstElementChild.cloneNode(true);

function node(tag, text, className) {
  const element = document.createElement(tag);
  if (text !== undefined) element.textContent = text;
  if (className) element.className = className;
  return element;
}

function setBusy(value) {
  busy = value;
  for (const id of ['send', 'reset', 'message', 'mode', 'level']) $(id).disabled = value;
  $('send').textContent = value ? 'Please wait…' : 'Send message';
  $('conversation').setAttribute('aria-busy', String(value));
}

async function api(path, options = {}) {
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
  return data;
}

function showError(error) {
  $('error').textContent = error instanceof TypeError ? 'The service is temporarily unavailable. Please try again shortly.' : error.message;
  $('error').hidden = false;
}

function addMessage(who, text, container = $('conversation')) {
  const article = node('article', undefined, `message ${who}`);
  article.append(node('p', who === 'learner' ? 'YOU' : 'TUTOR', 'speaker'), node('p', text));
  container.append(article);
  return article;
}

function renderReply(reply, container = $('conversation')) {
  const article = addMessage('tutor', reply.message, container);
  if (reply.evaluation) article.append(node('p', reply.evaluation.status.replaceAll('_', ' '), 'evaluation'));
  if (reply.correction) {
    article.append(node('h2', 'Your sentence'), node('p', reply.correction.original), node('h2', 'Suggested Japanese'), node('p', reply.correction.improved));
  }
  if (reply.explanation) article.append(node('h2', 'Explanation'), node('p', reply.explanation));
  if (reply.examples.length) {
    const list = node('ul');
    reply.examples.forEach((example) => list.append(node('li', example)));
    article.append(node('h2', 'Examples'), list);
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
    ? 'Ready · Ask a question or choose a learning task.' : health.setup_message;
}

async function resetSession() {
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
    if (savedSession) remember(`session-${placementLearnerId}`, sessionId);
    $('conversation').replaceChildren(welcome.cloneNode(true));
    $('message').value = '';
    $('mode').value = 'chat';
    updateCount();
    await refreshStatus();
  } catch (error) { showError(error); }
  finally { setBusy(false); $('message').focus(); }
}

function updateCount() { $('count').textContent = `${$('message').value.length} / 4,000 · Ctrl+Enter to send`; }

$('chat-form').addEventListener('submit', async (event) => {
  event.preventDefault();
  if (busy) return;
  const message = $('message').value.trim();
  if (!message) { showError(new Error('Enter a message or topic first.')); return; }
  if (!sessionId) { showError(new Error('Start a new session to connect to the tutor.')); return; }
  setBusy(true);
  $('error').hidden = true;
  $('status').textContent = 'The tutor is thinking…';
  try {
    const payload = { session_id: sessionId, message, mode: $('mode').value, level: $('level').value, learner_id: placementLearnerId };
    const signature = JSON.stringify(payload);
    if (!pendingChat || pendingChat.signature !== signature) pendingChat = { signature, id: crypto.randomUUID() };
    if (savedSession) payload.request_id = pendingChat.id;
    const data = await api('/api/chat', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload) });
    pendingChat = null;
    addMessage('learner', message);
    renderReply(data.response);
    $('message').value = '';
    if (data.response.exercise) $('mode').value = 'chat';
    updateCount();
    $('conversation').scrollTop = $('conversation').scrollHeight;
    $('status').textContent = 'Your turn · Take your time.';
  } catch (error) {
    showError(error);
    $('status').textContent = 'Your message is still in the editor. Retry, or start a new session if it expired.';
  } finally { setBusy(false); $('message').focus(); }
});
$('reset').addEventListener('click', resetSession);
$('message').addEventListener('input', updateCount);
$('message').addEventListener('keydown', (event) => {
  if (event.key === 'Enter' && (event.ctrlKey || event.metaKey) && !event.isComposing) {
    event.preventDefault(); $('chat-form').requestSubmit();
  }
});
