'use strict';
(() => {
  let installPrompt = null, installed = false, registrationStarted = false;
  const standalone = () => installed || Boolean(navigator.standalone || window.matchMedia?.('(display-mode: standalone)').matches);
  function installControls() {
    $('pwa-settings').hidden = standalone();
    $('pwa-install').hidden = standalone() || !installPrompt;
  }
  function waitingUpdate(registration) {
    if (registration.waiting && navigator.serviceWorker.controller) $('pwa-update').hidden = false;
  }
  async function register() {
    if (registrationStarted || !window.isSecureContext || !navigator.serviceWorker) return;
    registrationStarted = true;
    try {
      const registration = await navigator.serviceWorker.register('/service-worker.js', {scope:'/', updateViaCache:'none'});
      waitingUpdate(registration);
      registration.addEventListener('updatefound', () => {
        const worker = registration.installing;
        worker?.addEventListener('statechange', () => { if (worker.state === 'installed') waitingUpdate(registration); });
      });
      await navigator.serviceWorker.ready;
      if (!installed) $('pwa-status').textContent = 'Offline connection help is ready. Learning still needs an internet connection.';
    } catch {
      $('pwa-status').textContent = 'Offline connection help is unavailable in this browser session. You can still use GoiGrow online and follow your browser’s installation instructions.';
    }
  }
  window.addEventListener('beforeinstallprompt', event => {
    event.preventDefault(); installPrompt = event; installControls();
  });
  window.addEventListener('appinstalled', () => {
    installed = true; installPrompt = null; installControls();
  });
  window.matchMedia?.('(display-mode: standalone)').addEventListener?.('change', installControls);
  $('pwa-install').addEventListener('click', async () => {
    if (!installPrompt || standalone()) return;
    const prompt = installPrompt; installPrompt = null;
    $('pwa-install').disabled = true;
    try {
      await prompt.prompt(); const choice = await prompt.userChoice;
      if (!installed) $('pwa-status').textContent = choice.outcome === 'accepted'
        ? 'Follow your browser’s installation instructions. Open GoiGrow from your device to check the result.'
        : 'You can keep using GoiGrow here. Installation is optional.';
    } catch { $('pwa-status').textContent = 'Use your browser’s menu to add GoiGrow, or keep learning here.'; }
    finally { $('pwa-install').disabled = false; installControls(); }
  });
  installControls();
  // Register once after page load; no timer, polling, prompts or provider traffic.
  if (document.readyState === 'complete') register();
  else window.addEventListener('load', register, {once:true});
})();
