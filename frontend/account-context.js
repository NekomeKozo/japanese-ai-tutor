/* Server-resolved account ownership. Storage holds only a sign-in hint, never proof. */
'use strict';
const accountContext = (() => {
  const enabled = document.documentElement?.getAttribute('data-account-restoration') === 'true';
  let linked = false, checking = false;
  const channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('goigrow-account') : null;
  function clearHints() {
    for (const getStorage of [() => localStorage, () => sessionStorage]) {
      try {
        const storage = getStorage();
        const keys = Array.from({length:storage.length}, (_, i) => storage.key(i));
        for (const key of keys) if (key?.startsWith('japanese-tutor-')) storage.removeItem(key);
      } catch (_) { /* Storage may be unavailable; never use it for authorization. */ }
    }
  }
  function clear() {
    ++privateContextEpoch;
    linked = false; placementLearnerId = null; activeProfile = null;
    sessionId = null; savedSession = false; pendingChat = null; tutorOpenPending = false;
    assessmentState = null; pendingSubmission = null;
    clearHints();
    document.dispatchEvent(new Event('learner-changed'));
    $('conversation').replaceChildren(); $('message').value = '';
    for (const id of ['home-stats','home-focus','home-recent','profile-evidence','progress-overview','learning-history','learner-identity','placement-result','audio-progress','study-preview','study-content','study-choices','jlpt-feedback','practice-recap-content']) $(id).replaceChildren();
    for (const id of ['profile-summary','placement-context','review-summary','review-counts','review-forecast','study-feedback','study-purpose','study-progress-label','jlpt-prompt','jlpt-passage','jlpt-question-title']) $(id).textContent = '';
    $('profile-details').hidden = true;
    document.querySelectorAll('main form').forEach(form => form.reset());
  }
  function leave(path = '/auth/sign-in') {
    if (document.documentElement) document.documentElement.hidden = true;
    clear(); window.location.assign(path);
  }
  async function resolve() {
    if (!enabled) return {state:'legacy'};
    const epoch = privateContextEpoch;
    const response = await fetch('/api/account/learner', {credentials:'same-origin', cache:'no-store'});
    if (epoch !== privateContextEpoch) throw new Error('Your account context changed. Sign in again.');
    if (response.status === 401) {
      let expected = false;
      try { expected = localStorage.getItem('goigrow-account-mode') === '1'; } catch (_) { /* Optional hint. */ }
      if (expected) { leave(); throw new Error('Sign in to restore your learning profile.'); }
      return {state:'legacy'};
    }
    if (!response.ok) throw new Error('Your account’s learning profile could not be checked. Retry when connected. Nothing has been reset.');
    const data = await response.json();
    if (epoch !== privateContextEpoch) throw new Error('Your account context changed. Sign in again.');
    clear();
    try { localStorage.setItem('goigrow-account-mode', '1'); } catch (_) { /* Optional hint. */ }
    if (data.state !== 'linked' || !data.learner_id) {
      leave(); throw new Error('Open your account to link your original learning profile.');
    }
    linked = true;
    $('account-learning-status').hidden = false;
    $('account-learning-status').textContent = 'Your linked learning profile was restored securely. Your saved progress is unchanged.';
    const tools = document.getElementById('legacy-profile-tools'); if (tools) tools.hidden = true;
    $('placement-intro').hidden = true;
    $('account-placement-notice').hidden = false;
    $('fresh-profile').disabled = true;
    return data;
  }
  channel?.addEventListener('message', () => leave());
  window.addEventListener('pagehide', () => {
    if (!enabled && !linked) return;
    if (document.documentElement) document.documentElement.hidden = true;
    clear(); channel?.close();
  });
  window.addEventListener('pageshow', event => { if (enabled && event.persisted) window.location.reload(); });
  // Recheck after another tab changes cookies, even when BroadcastChannel is unavailable.
  async function recheck() {
    if (!enabled || !linked || checking) return;
    checking = true;
    const epoch = privateContextEpoch, learner = placementLearnerId;
    if (document.documentElement) document.documentElement.hidden = true;
    try {
      const response = await fetch('/api/account/learner', {credentials:'same-origin', cache:'no-store'});
      const data = response.ok ? await response.json() : null;
      if (epoch !== privateContextEpoch) return;
      if (data?.state !== 'linked' || data.learner_id !== learner) { leave(); return; }
      if (document.documentElement) document.documentElement.hidden = false;
    } catch (_) { leave(); }
    finally { checking = false; }
  }
  window.addEventListener('focus', () => void recheck());
  document.addEventListener('visibilitychange', () => { if (!document.hidden) void recheck(); });
  return {resolve, clear, leave, linked:() => linked};
})();
