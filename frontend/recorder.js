'use strict';

function createBrowserRecorder({secure, mediaDevices, Recorder, BlobType, urls,
  now = () => performance.now(), schedule = setTimeout, unschedule = clearTimeout,
  repeat = setInterval, unrepeat = clearInterval, beforeStart = () => {},
  maxDurationMs = 60000, maxBytes = 8 * 1024 * 1024}) {
  const availability = !secure ? 'insecure' :
    (mediaDevices?.getUserMedia && Recorder && BlobType && urls?.createObjectURL && urls?.revokeObjectURL ? 'supported' : 'unsupported');
  let phase = 'idle', message = '', elapsedMs = 0, permissionPending = false, epoch = 0;
  let stream = null, recorder = null, chunks = [], bytes = 0, clip = null, url = '', startedAt = 0;
  let ticker = null, deadline = null, finishTimer = null;
  const trackHandlers = new Map(), listeners = new Set();
  const state = () => ({availability,phase,message,elapsedMs,permissionPending,url,bytes:clip?.size || bytes,mimeType:clip?.type || ''});
  function notify() { for (const listener of [...listeners]) listener(state()); }
  function clearTimers() {
    if (ticker !== null) unrepeat(ticker);
    if (deadline !== null) unschedule(deadline);
    if (finishTimer !== null) unschedule(finishTimer);
    ticker = deadline = finishTimer = null;
  }
  function stopTracks(mediaStream) {
    for (const track of mediaStream?.getTracks() || []) {
      const handler = trackHandlers.get(track);
      if (handler) { track.removeEventListener?.('ended',handler); trackHandlers.delete(track); }
      try { track.stop(); } catch { /* Release other tracks too. */ }
    }
  }
  function releaseStream() { stopTracks(stream); stream = null; }
  function releaseCapture() {
    clearTimers();
    if (recorder) {
      recorder.ondataavailable = recorder.onstop = recorder.onerror = null;
      try { if (recorder.state !== 'inactive') recorder.stop(); } catch { /* Tracks are still stopped below. */ }
      recorder = null;
    }
    releaseStream(); chunks = []; bytes = 0;
  }
  function dropClip() { if (url) urls.revokeObjectURL(url); url = ''; clip = null; }
  function cancel(note = 'Recording discarded.') {
    ++epoch; releaseCapture(); dropClip(); elapsedMs = 0; phase = 'idle';
    message = permissionPending ? 'Request cancelled. Close the microphone prompt; any returned microphone will be released. Reload if the prompt does not close.' : note;
    notify();
  }
  function fail(token, note) {
    if (token !== epoch) return;
    cancel(''); phase = 'error'; message = note; notify();
  }
  function permissionError(error) {
    return {
      NotAllowedError:'Microphone permission was denied. Allow microphone access in your browser settings, then press Record to retry.',
      SecurityError:'Microphone access is blocked by this browser or page. Use the secure GoiGrow website and check your browser settings.',
      NotFoundError:'No microphone was found. Connect or enable a microphone, then retry.',
      NotReadableError:'The microphone could not be opened. It may be in use by another app; close that app and retry.',
      AbortError:'Microphone access was interrupted. Press Record to try again.',
      OverconstrainedError:'This microphone is not available for recording. Try another device.',
      NotSupportedError:'This browser could not initialize audio recording. Try another supported browser.'
    }[error?.name] || 'Recording could not start. Check your microphone and try again.';
  }
  function mimeOptions() {
    if (typeof Recorder.isTypeSupported !== 'function') return undefined;
    const candidates = ['audio/webm;codecs=opus','audio/webm','audio/mp4;codecs=mp4a.40.2','audio/mp4','audio/ogg;codecs=opus'];
    try { const mimeType = candidates.find(type => Recorder.isTypeSupported(type)); return mimeType ? {mimeType} : undefined; }
    catch { return undefined; }
  }
  function stop(note = 'Microphone off. Preparing your local preview…') {
    if (phase !== 'recording') return;
    const token = epoch;
    elapsedMs = Math.max(0,now() - startedAt); phase = 'processing'; message = note;
    clearTimers(); notify();
    finishTimer = schedule(() => fail(token,'The recording could not finish. The microphone is off; please record again.'),5000);
    try { recorder.stop(); releaseStream(); }
    catch { fail(token,'The recording could not finish. Please record again.'); }
  }
  async function start() {
    if (permissionPending || ['requesting','recording','processing'].includes(phase)) return;
    if (availability !== 'supported') {
      phase = 'error'; message = availability === 'insecure' ? 'Microphone recording needs HTTPS or localhost. Open the secure GoiGrow website.' : 'Audio recording is unavailable in this browser. Try a current Chrome, Edge, Firefox or Safari browser.'; notify(); return;
    }
    beforeStart(); cancel('');
    const token = epoch; phase = 'requesting'; permissionPending = true; message = 'Waiting for microphone permission. You can cancel this request.'; notify();
    try {
      const granted = await mediaDevices.getUserMedia({audio:true,video:false});
      if (token !== epoch) { stopTracks(granted); return; }
      stream = granted;
      const tracks = stream.getAudioTracks();
      if (!tracks.length || tracks.every(track => track.readyState === 'ended')) throw {name:'NotFoundError'};
      const options = mimeOptions();
      try { recorder = options ? new Recorder(stream,options) : new Recorder(stream); }
      catch (error) { if (!options || error.name !== 'NotSupportedError') throw error; recorder = new Recorder(stream); }
      for (const track of tracks) {
        const ended = () => { if (token === epoch && phase === 'recording') fail(token,'The microphone disconnected or recording was interrupted. Please record again.'); };
        trackHandlers.set(track,ended); track.addEventListener?.('ended',ended);
      }
      recorder.ondataavailable = event => {
        if (token !== epoch || !['recording','processing'].includes(phase) || !event.data?.size) return;
        if (bytes + event.data.size > maxBytes) { fail(token,'The recording reached the 8 MB size limit and was discarded. Try a shorter recording.'); return; }
        bytes += event.data.size; chunks.push(event.data);
      };
      recorder.onerror = () => fail(token,'Recording failed or was interrupted. The microphone is off; please record again.');
      recorder.onstop = () => {
        if (token !== epoch) return;
        if (phase !== 'processing') { fail(token,'Recording stopped unexpectedly. Please record again.'); return; }
        try {
          const mimeType = recorder.mimeType || chunks.find(chunk => chunk.type)?.type || '';
          const result = new BlobType(chunks,{type:mimeType});
          releaseCapture();
          if (!result.size) { fail(token,'No audio was recorded. Try recording a little longer.'); return; }
          clip = result; url = urls.createObjectURL(clip); phase = 'preview';
          message = noteForPreview(message); notify();
        } catch { fail(token,'The local preview could not be created. Please record again.'); }
      };
      startedAt = now(); elapsedMs = 0; phase = 'recording'; message = 'Recording · microphone on.';
      recorder.start(250);
      if (token !== epoch) return;
      ticker = repeat(() => { if (phase !== 'recording') return; elapsedMs = Math.max(0,now() - startedAt); if (elapsedMs >= maxDurationMs) stop('60-second limit reached. Microphone off.'); else notify(); },250);
      deadline = schedule(() => stop('60-second limit reached. Microphone off.'),maxDurationMs);
      notify();
    } catch (error) { fail(token,permissionError(error)); }
    finally { permissionPending = false; notify(); }
  }
  function noteForPreview(note) {
    return note.startsWith('60-second') ? '60-second limit reached. Microphone off; your local preview is ready.' : 'Microphone off. Preview stays in this tab and has not been sent to AI.';
  }
  return {
    state,start,stop,cancel,
    recording: () => clip ? {blob:clip,mimeType:clip.type,durationMs:elapsedMs} : null,
    subscribe(listener) { listeners.add(listener); listener(state()); return () => listeners.delete(listener); },
    destroy() { cancel(''); listeners.clear(); }
  };
}

function pauseRecordingPreview() { $('recording-preview').pause(); }
const browserRecorder = createBrowserRecorder({secure:window.isSecureContext === true,
  mediaDevices:navigator.mediaDevices, Recorder:window.MediaRecorder, BlobType:window.Blob, urls:window.URL,
  beforeStart:() => { pauseRecordingPreview(); japaneseAudio.stop(); }});
let recordingPreviewUrl = '';
function recordingText(element,value) { if (element.textContent !== value) element.textContent = value; }
browserRecorder.subscribe(state => {
  const capturing = ['requesting','recording'].includes(state.phase);
  japaneseAudio.setBlocked(capturing);
  const active = ['requesting','recording','processing'].includes(state.phase);
  $('recording-start').disabled = state.availability !== 'supported' || active || state.permissionPending;
  $('recording-start').textContent = state.phase === 'preview' ? 'Record again' : 'Record';
  $('recording-stop').hidden = state.phase !== 'recording'; $('recording-cancel').hidden = !active;
  $('recording-play').hidden = $('recording-discard').hidden = state.phase !== 'preview';
  $('recording-preview').hidden = state.phase !== 'preview';
  if (recordingPreviewUrl !== state.url) {
    pauseRecordingPreview(); recordingPreviewUrl = state.url;
    if (state.url) $('recording-preview').src = state.url;
    else $('recording-preview').removeAttribute('src');
    $('recording-preview').load(); $('recording-preview-error').hidden = true;
  }
  const seconds = Math.floor(state.elapsedMs / 1000);
  recordingText($('recording-timer'),`${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2,'0')} / 1:00`);
  $('recording-timer').hidden = !['recording','processing','preview'].includes(state.phase);
  $('recording-status').setAttribute('data-recording',String(state.phase === 'recording'));
  recordingText($('recording-status'),state.message || (state.availability === 'insecure' ? 'Recording needs HTTPS or localhost.' : state.availability === 'unsupported' ? 'Audio recording is unavailable in this browser.' : 'Microphone off. Press Record when you’re ready.'));
  $('recording-error').hidden = state.phase !== 'error'; recordingText($('recording-error'),state.phase === 'error' ? state.message : '');
});
japaneseAudio.subscribe(state => { if (state.owner) pauseRecordingPreview(); });
$('recording-start').addEventListener('click',() => browserRecorder.start());
$('recording-stop').addEventListener('click',() => browserRecorder.stop());
$('recording-cancel').addEventListener('click',() => browserRecorder.cancel());
$('recording-discard').addEventListener('click',() => browserRecorder.cancel());
$('recording-play').addEventListener('click',async () => {
  if (browserRecorder.state().phase !== 'preview') return;
  const previewUrl = browserRecorder.state().url;
  $('recording-preview-error').hidden = true; japaneseAudio.stop();
  try { $('recording-preview').currentTime = 0; await $('recording-preview').play(); }
  catch { if (browserRecorder.state().phase === 'preview' && browserRecorder.state().url === previewUrl) showRecordingPreviewError(); }
});
function showRecordingPreviewError() {
  $('recording-preview-error').textContent = 'This browser could not play the recording. Record again or try another browser.';
  $('recording-preview-error').hidden = false;
}
$('recording-preview').addEventListener('play',() => { if (browserRecorder.state().phase !== 'preview') pauseRecordingPreview(); else japaneseAudio.stop(); });
$('recording-preview').addEventListener('error',() => { if (browserRecorder.state().phase === 'preview') showRecordingPreviewError(); });
$('recording-card').addEventListener('toggle',() => { if (!$('recording-card').open) browserRecorder.cancel(); });
window.addEventListener('hashchange',() => { pauseRecordingPreview(); browserRecorder.cancel('Recording discarded when leaving this page.'); });
window.addEventListener('pagehide',() => { pauseRecordingPreview(); browserRecorder.cancel(''); });
document.addEventListener('visibilitychange',() => {
  if (!document.hidden) return;
  pauseRecordingPreview();
  if (['requesting','recording','processing'].includes(browserRecorder.state().phase) || browserRecorder.state().permissionPending) browserRecorder.cancel('Recording cancelled when the tab was hidden.');
});
document.addEventListener('learner-changed',() => { pauseRecordingPreview(); browserRecorder.cancel(''); });
