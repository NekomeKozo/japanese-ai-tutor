/* Account UI stores no provider credentials or account/profile IDs. */
(() => {
  'use strict';
  const $ = (id) => document.getElementById(id);
  const status = $('account-status'), error = $('account-error');
  let csrf = '', busy = false;
  let screen = location.pathname === '/auth/recovery' ? 'reset' : location.pathname === '/auth/callback' ? 'invite' : 'login';
  // Default Supabase links can redirect with provider tokens in the fragment.
  // Do not accept, store or submit those tokens. Remove them immediately.
  const redirected = Boolean(location.hash || location.search);
  history.replaceState(null, '', location.pathname);
  const channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('goigrow-account') : null;
  channel?.addEventListener('message', () => location.reload());
  const announce = () => channel?.postMessage('changed');
  const clearSecrets = () => document.querySelectorAll('input[type="password"]').forEach((field) => { field.value = ''; });
  function show(next) {
    screen = next;
    const active = { login: 'login-form', invite: 'link-form', reset: 'link-form', forgot: 'recovery-form', password: 'password-form', ready: 'account-ready', gate: 'gate-form' }[next];
    ['login-form', 'link-form', 'recovery-form', 'password-form', 'account-ready', 'gate-form'].forEach((id) => { $(id).hidden = id !== active; });
    $('account-options').hidden = ['ready', 'password', 'gate'].includes(next);
    $('account-title').textContent = { login: 'Sign in', invite: 'Accept your invitation', reset: 'Use your recovery link', forgot: 'Forgot password', password: 'Choose your password', ready: 'Your account is ready', gate: 'Open account sign-in' }[next];
    $('link-instructions').textContent = next === 'reset' ? 'In your recovery email, copy the “Reset password” link without opening it. Paste it below to verify it securely.' : 'In your invitation email, copy the “Accept invitation” link without opening it. Paste it below to verify your email securely.';
    clearSecrets(); error.hidden = true;
  }
  async function request(path, body, flow) {
    const response = await fetch('/api/' + path, { method: body === undefined ? 'GET' : 'POST', credentials: 'same-origin', cache: 'no-store',
      headers: { 'Content-Type': 'application/json', ...(body === undefined ? {} : { 'X-CSRF-Token': csrf }), ...(flow ? { 'X-Account-Flow': flow } : {}) },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }) });
    const data = await response.json();
    if (!response.ok) {
      const failure = new Error(data.error?.message || 'Please try again.');
      failure.code = data.error?.code; failure.status = response.status; throw failure;
    }
    return data;
  }
  async function bootstrap() { csrf = (await request('account/bootstrap')).csrf; }
  async function initialize() {
    try {
      await bootstrap();
      let state;
      try { state = await request('account/me'); } catch (failure) { if (failure.status !== 401) throw failure; }
      show(state?.state === 'ready' ? 'ready' : ['activation', 'recovery'].includes(state?.state) ? 'password' : screen);
      status.textContent = redirected ? 'For secure verification, copy the original email link and paste it here. If it was already opened, ask for a fresh invitation or recovery email.' : state ? 'Email verified.' : 'Sign in with your invited, verified email.';
    } catch (failure) {
      if (failure.code === 'staging_access_required') { show('gate'); status.textContent = 'Staging access is required.'; }
      else { show('login'); document.querySelectorAll('form button, #account-options button').forEach((button) => { button.disabled = true; }); status.textContent = 'Account sign-in is currently unavailable. Your existing learning space is unaffected.'; }
    }
  }
  async function action(form, work) {
    if (busy) return;
    busy = true; form?.setAttribute('aria-busy', 'true'); error.hidden = true;
    document.querySelectorAll('button').forEach((button) => { button.disabled = true; }); status.textContent = 'Please wait…';
    try { await work(); }
    catch (failure) {
      if (failure.status === 401) { error.textContent = 'Sign-in or verification failed. Check your details, verified email and invitation. Links can expire or be used only once.'; }
      else { error.textContent = failure.message || 'Connection interrupted. Please try again.'; }
      error.hidden = false; status.textContent = '';
      if (['ready', 'password'].includes(screen) && [401, 403].includes(failure.status)) {
        announce(); show('login'); status.textContent = 'Your account session may have expired. Sign in again to continue.';
      }
      if (failure.status === 403 || failure.status === 401) { try { await bootstrap(); } catch (_) { /* Retry remains explicit. */ } }
    } finally { busy = false; form?.removeAttribute('aria-busy'); document.querySelectorAll('button').forEach((button) => { button.disabled = false; }); clearSecrets(); }
  }
  document.querySelectorAll('[data-screen]').forEach((button) => button.addEventListener('click', () => { show(button.dataset.screen); status.textContent = ''; $('account-title').focus(); }));
  function submit(id, work) { $(id).addEventListener('submit', (event) => { event.preventDefault(); void action($(id), work); }); }
  submit('gate-form', async () => { await request('access', { code: $('gate-code').value }); screen = location.pathname === '/auth/recovery' ? 'reset' : 'login'; await initialize(); });
  submit('login-form', async () => { await request('account/login', { email: $('login-email').value, password: $('login-password').value }); announce(); await bootstrap(); show('ready'); status.textContent = 'Signed in securely.'; });
  submit('link-form', async () => { await request('account/accept', { email: $('link-email').value, link: $('email-link').value }, screen === 'reset' ? 'recovery' : 'invite'); announce(); await bootstrap(); show('password'); status.textContent = 'Email verified. Choose a password to finish.'; });
  submit('recovery-form', async () => { const data = await request('account/recover', { email: $('recovery-email').value }); status.textContent = data.message; });
  submit('password-form', async () => { if ($('new-password').value !== $('confirm-password').value) throw new Error('The passwords must match.'); const data = await request('account/password', { password: $('new-password').value }); announce(); await bootstrap(); show('login'); status.textContent = data.message; });
  $('logout').addEventListener('click', () => void action(null, async () => { await request('account/logout', {}); announce(); await bootstrap(); show('login'); status.textContent = 'Signed out of this browser.'; }));
  window.addEventListener('pagehide', () => { clearSecrets(); csrf = ''; channel?.close(); });
  window.addEventListener('pageshow', (event) => { if (event.persisted) location.reload(); });
  void initialize();
})();
