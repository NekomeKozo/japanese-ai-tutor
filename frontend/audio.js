'use strict';

// One speech queue for the whole page. Never sends requests to the tutor backend.
function createJapaneseAudio({synth, Utterance, schedule = setTimeout, unschedule = clearTimeout}) {
  const supported = Boolean(synth && Utterance && typeof synth.getVoices === 'function');
  let voices = [], selected = '', rate = 1, phase = 'idle', availability = supported ? 'loading' : 'unsupported';
  let owner = null, utterance = null, generation = 0, watchdog = null, voiceTimer = null, message = '';
  const listeners = new Set();
  let blocked = false;
  const key = voice => `${voice.voiceURI || voice.name}|${voice.lang}|${voice.name}`;
  const state = () => ({voices: voices.map(v => ({id:key(v), name:v.name, lang:v.lang})), selected, rate, phase, availability, owner, message, blocked});
  function notify() { for (const listener of [...listeners]) listener(state()); }
  function detach() {
    if (watchdog !== null) unschedule(watchdog);
    watchdog = null;
    if (utterance) utterance.onstart = utterance.onend = utterance.onerror = null;
    utterance = null;
  }
  function stop(note = '') {
    ++generation; detach();
    if (supported) { try { synth.cancel(); } catch { /* UI can still reset. */ } }
    phase = 'idle'; owner = null; message = note; notify();
  }
  function refresh() {
    if (!supported) return;
    try { voices = synth.getVoices().filter(v => /^ja(?:[-_]|$)/i.test(v.lang)); }
    catch { voices = []; }
    voices.sort((a,b) => Number(Boolean(b.localService)) - Number(Boolean(a.localService)) || Number(/^ja[-_]JP$/i.test(b.lang)) - Number(/^ja[-_]JP$/i.test(a.lang)));
    if (!voices.some(v => key(v) === selected)) {
      if (owner !== null) stop('The selected voice changed. Choose a voice and replay.');
      selected = voices[0] ? key(voices[0]) : '';
    }
    availability = voices.length ? 'ready' : (voiceTimer !== null ? 'loading' : 'missing');
    notify();
  }
  function fail(token) {
    if (token !== generation) return;
    stop(); phase = 'error'; message = 'Audio could not play. Check your device’s Japanese voice or try Play again.'; notify();
  }
  function play(text, id) {
    if (blocked) return false;
    refresh();
    if (!selected || !String(text).trim()) return false;
    if (text.length > 12000) { stop('Choose a shorter Japanese passage to play.'); return false; }
    stop(); owner = id; phase = 'starting'; message = ''; const token = generation;
    const voice = voices.find(v => key(v) === selected);
    // Short chunks avoid long-utterance stalls in browser speech engines.
    const chunks = [];
    for (const sentence of String(text).match(/[^。！？\n]+[。！？\n]?/gu) || []) {
      if (sentence.length <= 160 && chunks.length && chunks[chunks.length - 1].length + sentence.length <= 160) chunks[chunks.length - 1] += sentence;
      else chunks.push(...(sentence.match(/[\s\S]{1,160}/gu) || []));
    }
    let index = 0;
    function next() {
      if (token !== generation) return;
      detach();
      if (index === chunks.length) { phase = 'idle'; owner = null; message = 'Playback finished.'; notify(); return; }
      try {
        utterance = new Utterance(chunks[index++]); utterance.lang = voice.lang; utterance.voice = voice; utterance.rate = rate;
        utterance.onstart = () => {
          if (token !== generation) return;
          phase = 'playing'; notify();
          if (watchdog !== null) unschedule(watchdog);
          watchdog = schedule(() => fail(token), 90000);
        };
        utterance.onend = next; utterance.onerror = () => fail(token);
        watchdog = schedule(() => fail(token), 10000);
        synth.speak(utterance); notify();
      } catch { fail(token); }
    }
    next(); return phase !== 'error';
  }
  if (supported) {
    voiceTimer = schedule(() => { voiceTimer = null; refresh(); }, 4000);
    if (typeof synth.addEventListener === 'function') synth.addEventListener('voiceschanged', refresh);
    refresh();
  }
  return {
    state, play, stop, refresh,
    setBlocked(value) { if (blocked === Boolean(value)) return; blocked = Boolean(value); if (blocked) stop(); else notify(); },
    setVoice(id) { if (!voices.some(v => key(v) === id)) return; stop('Voice changed. Press Play to hear it.'); selected = id; notify(); },
    setRate(value) { const next = Number(value); if (![0.75,1,1.25].includes(next)) return; stop('Speed changed. Press Play to hear it.'); rate = next; notify(); },
    subscribe(listener) { listeners.add(listener); listener(state()); return () => listeners.delete(listener); },
    destroy() { stop(); if (voiceTimer !== null) unschedule(voiceTimer); synth?.removeEventListener?.('voiceschanged', refresh); listeners.clear(); }
  };
}

const japaneseAudio = createJapaneseAudio({synth:window.speechSynthesis, Utterance:window.SpeechSynthesisUtterance});
let audioControlSequence = 0;
// Only explicit public reply fields call this extractor; no metadata or DOM scraping.
function japanesePlaybackText(text) {
  return (String(text || '').match(/[\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Han}0-9０-９。、！？「」『』（）ー〜・\s]+/gu) || [])
    .map(part => part.trim()).filter(part => /[\p{Script=Hiragana}\p{Script=Katakana}\p{Script=Han}]/u.test(part)).join('\n');
}
function audioElement(tag, text, className) {
  const element = document.createElement(tag); if (text !== undefined) element.textContent = text;
  if (className) element.className = className; return element;
}
function attachJapaneseAudio(container, text, label = 'Japanese text', onStarted = () => {}) {
  const spoken = japanesePlaybackText(text); if (!spoken) return null;
  const id = `audio-${++audioControlSequence}`;
  const player = audioElement('div', undefined, 'audio-player'); player.setAttribute('role','group'); player.setAttribute('aria-label',`Audio: ${label}`);
  const actions = audioElement('div', undefined, 'audio-actions');
  const play = audioElement('button','Play audio','secondary'); play.type = 'button';
  const stop = audioElement('button','Stop','secondary'); stop.type = 'button';
  const voiceLabel = audioElement('label','Japanese voice'); const voiceSelect = audioElement('select'); voiceLabel.append(voiceSelect);
  const speedLabel = audioElement('label','Speed'); const speed = audioElement('select');
  voiceSelect.setAttribute('aria-label','Japanese voice'); speed.setAttribute('aria-label','Speed');
  for (const [value,title] of [[0.75,'0.75× · Slow'],[1,'1.0× · Normal'],[1.25,'1.25× · Fast']]) { const option = audioElement('option',title); option.value = String(value); speed.append(option); }
  speedLabel.append(speed);
  const status = audioElement('p',undefined,'audio-status small'); status.setAttribute('role','status');
  actions.append(play,stop); player.append(actions,voiceLabel,speedLabel,status); container.append(player);
  let signature = '', started = false, unsubscribe = () => {};
  unsubscribe = japaneseAudio.subscribe(state => {
    if (player.isConnected === false) { unsubscribe(); return; }
    const next = JSON.stringify(state.voices);
    if (next !== signature) {
      signature = next; voiceSelect.replaceChildren();
      for (const voice of state.voices) { const option = audioElement('option',`${voice.name} (${voice.lang})`); option.value = voice.id; voiceSelect.append(option); }
    }
    voiceSelect.value = state.selected; voiceSelect.disabled = state.availability !== 'ready' || state.blocked; speed.value = String(state.rate); speed.disabled = state.blocked;
    play.disabled = state.availability !== 'ready' || state.blocked;
    const active = state.owner === id; stop.disabled = !active;
    play.textContent = active ? 'Replay audio' : 'Play audio';
    status.textContent = state.blocked ? 'Finish or cancel microphone recording to play Japanese audio.' : {
      unsupported:'Audio is unavailable in this browser. Try a browser with Japanese text-to-speech support.',
      loading:'Looking for Japanese voices…',
      missing:'No Japanese voice is available. Enable a Japanese speech voice in your device settings, then reload. Listening transcripts remain available.'
    }[state.availability] || (active ? (state.phase === 'starting' ? 'Preparing audio…' : 'Playing Japanese audio.') : state.message || 'Ready · press Play audio.');
    if (active && state.phase === 'playing' && !started) { started = true; onStarted(); }
  });
  play.addEventListener('click', () => { started = false; japaneseAudio.play(spoken,id); });
  stop.addEventListener('click', () => japaneseAudio.stop('Playback stopped.'));
  speed.addEventListener('change', () => japaneseAudio.setRate(speed.value));
  voiceSelect.addEventListener('change', () => japaneseAudio.setVoice(voiceSelect.value));
  return {destroy() { unsubscribe(); if (japaneseAudio.state().owner === id) japaneseAudio.stop(); }};
}
window.addEventListener('hashchange', () => japaneseAudio.stop());
window.addEventListener('pagehide', () => japaneseAudio.stop());
document.addEventListener('visibilitychange', () => { if (document.hidden) japaneseAudio.stop(); });
document.addEventListener('learner-changed', () => japaneseAudio.stop());
