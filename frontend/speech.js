'use strict';

function encodeSpeechWav(samples, BlobType = Blob) {
  if (!samples.length || samples.length > 960000) throw new Error('Record between a moment and 60 seconds.');
  const buffer = new ArrayBuffer(44 + samples.length * 2), view = new DataView(buffer);
  const text = (offset,value) => { for (let i=0;i<value.length;i++) view.setUint8(offset+i,value.charCodeAt(i)); };
  text(0,'RIFF'); view.setUint32(4,buffer.byteLength-8,true); text(8,'WAVE'); text(12,'fmt ');
  view.setUint32(16,16,true); view.setUint16(20,1,true); view.setUint16(22,1,true);
  view.setUint32(24,16000,true); view.setUint32(28,32000,true); view.setUint16(32,2,true); view.setUint16(34,16,true);
  text(36,'data'); view.setUint32(40,samples.length*2,true);
  for (let i=0;i<samples.length;i++) {
    if (!Number.isFinite(samples[i])) throw new Error('This recording could not be prepared. Record again.');
    const value = Math.max(-1,Math.min(1,samples[i])); view.setInt16(44+i*2,Math.round(value*(value<0?32768:32767)),true);
  }
  return new BlobType([buffer],{type:'audio/wav'});
}

async function prepareSpeechAudio(recording,signal) {
  const Context = window.AudioContext || window.webkitAudioContext;
  const Offline = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  if (!Context || !Offline) throw new Error('This browser cannot prepare audio for transcription. Your preview is still here; try a current browser.');
  if (!recording.blob.size || recording.blob.size > 8*1024*1024) throw new Error('Record a shorter Japanese sentence.');
  let context;
  const close = () => { if (context && context.state !== 'closed') context.close().catch(()=>{}); };
  signal.addEventListener('abort',close,{once:true});
  try {
    if (signal.aborted) throw new Error('Cancelled.');
    context = new Context();
    const decoded = await context.decodeAudioData(await recording.blob.arrayBuffer());
    if (signal.aborted) throw new Error('Cancelled.');
    // Validate decoded duration, never the recorder timer or client metadata.
    if (!Number.isFinite(decoded.duration) || decoded.duration <= 0 || decoded.duration > 60) throw new Error('Record no more than 60 seconds.');
    if (decoded.numberOfChannels > 2) throw new Error('This recording format is unsupported. Record again.');
    const frames = Math.ceil(decoded.duration*16000), offline = new Offline(1,frames,16000);
    const source = offline.createBufferSource(); source.buffer = decoded;
    source.connect(offline.destination); source.start();
    const rendered = await offline.startRendering();
    if (signal.aborted) throw new Error('Cancelled.');
    return encodeSpeechWav(rendered.getChannelData(0),window.Blob);
  } catch(error) {
    if (error.name === 'EncodingError' || error.name === 'NotSupportedError') throw new Error('This browser cannot decode its recording for transcription. Your preview is still here; try another browser.');
    throw error;
  } finally { signal.removeEventListener('abort',close); close(); }
}

function createSpeechTranscriber({recorder,prepare,send,newId,AbortType=AbortController,
  schedule=setTimeout,unschedule=clearTimeout}) {
  let phase='idle',original='',edited='',message='',epoch=0,controller=null,timer=null,preparing=false;
  let clipUrl=recorder.state().url;
  const listeners=new Set();
  const state=()=>({phase,original,edited,message,preparing});
  const notify=()=>{for(const fn of listeners)fn(state());};
  function cancel(note='Transcription cancelled. Your recording is still available.') {
    ++epoch;controller?.abort();controller=null;if(timer!==null)unschedule(timer);timer=null;
    phase=original?'editing':'idle';message=note;notify();
  }
  function reset() { cancel('');original=edited='';phase='idle';notify(); }
  recorder.subscribe(s=>{if(s.url!==clipUrl){clipUrl=s.url;reset();}});
  async function transcribe(learnerId) {
    if (preparing || ['preparing','uploading'].includes(phase)) return;
    if (!learnerId) { phase='error';message='Finish setting up your learner profile before transcription.';notify();return; }
    const recording=recorder.recording();
    if (!recording || recorder.state().phase!=='preview') return;
    cancel('');const token=epoch;controller=new AbortType();const signal=controller.signal;
    phase='preparing';preparing=true;message='Preparing your recording locally…';notify();
    timer=schedule(()=>{if(token===epoch){cancel('Transcription took too long. Your recording is still here; retry.');phase='error';notify();}},45000);
    try {
      const wav=await prepare(recording,signal);
      if(token!==epoch)return;
      phase='uploading';message='Transcribing with Groq…';notify();
      const result=await send(learnerId,wav,newId(),signal);
      if(token!==epoch)return;
      if(result?.language!=='ja' || result?.provider!=='groq' || typeof result.original_text!=='string' || !result.original_text.trim() || result.original_text.length>4000) throw new Error('The transcript could not be read. Please retry.');
      original=edited=result.original_text;phase='editing';message='Review and edit the Japanese transcript, then confirm text.';
    } catch(error) {
      if(token!==epoch)return;
      phase='error';message=error instanceof TypeError || error instanceof SyntaxError ? 'Transcription could not connect. Your recording is still here; please retry.' : error.message || 'Transcription failed. Your recording is still here; retry.';
    } finally {
      preparing=false;
      if(token===epoch){if(timer!==null)unschedule(timer);timer=null;controller=null;}
      notify();
    }
  }
  function edit(value){edited=String(value).slice(0,4000);notify();}
  function confirm(apply) {
    if(!original || ['preparing','uploading'].includes(phase))return;
    const text=edited.trim();
    if(!text){message='Enter the Japanese text you want to use.';notify();return;}
    const issue=apply(text);
    message=issue || 'Text copied to the message box. Review it and press Send message when ready.';notify();
  }
  return {state,transcribe,cancel,reset,edit,confirm,subscribe(fn){listeners.add(fn);fn(state());return()=>listeners.delete(fn);}};
}

async function sendSpeechAudio(learnerId,wav,id,signal) {
  const response=await fetch(`/api/learners/${encodeURIComponent(learnerId)}/speech/transcribe`,{
    method:'POST',headers:{'Content-Type':'audio/wav','X-Transcription-ID':id},body:wav,signal,credentials:'same-origin'});
  if(response.status===401){window.location.assign('/access');throw new Error('Sign in to continue.');}
  const result=await response.json();
  if(!response.ok)throw new Error(result.error?.message || 'Transcription failed. Please retry.');
  return result;
}
const speechTranscriber=createSpeechTranscriber({recorder:browserRecorder,prepare:prepareSpeechAudio,
  send:sendSpeechAudio,newId:()=>crypto.randomUUID(),AbortType:window.AbortController});
let speechEnabled=false,speechConfigPending=false;
async function loadSpeechConfiguration() {
  if(speechConfigPending)return;
  speechConfigPending=true;$('speech-config-status').textContent='Checking transcription availability…';
  try {
    const config=await api('/api/speech/config');speechEnabled=config.enabled===true;
    $('speech-config-status').textContent=speechEnabled?'Transcription sends your audio to Groq only when you press Transcribe audio.':config.setup_message || 'Transcription is not enabled yet. Local preview still works.';
    $('speech-config-retry').hidden=speechEnabled;
  } catch {
    speechEnabled=false;$('speech-config-status').textContent='Transcription availability could not be checked. Local preview still works.';$('speech-config-retry').hidden=false;
  } finally {speechConfigPending=false;renderSpeechControls();}
}
function renderSpeechControls() {
  const s=speechTranscriber.state(),preview=browserRecorder.state().phase==='preview';
  const active=['preparing','uploading'].includes(s.phase);
  $('speech-controls').setAttribute('aria-busy',String(active));
  $('speech-transcribe').hidden=!preview;$('speech-transcribe').disabled=!speechEnabled || active || s.preparing || Boolean(s.original);
  $('speech-transcribe').textContent=active?'Transcribing…':s.original?'Transcribed':s.phase==='error'?'Retry transcription':'Transcribe audio';
  $('speech-cancel').hidden=!active;
  $('speech-result').hidden=!s.original || !preview;
  $('speech-transcript').disabled=active;
  if($('speech-transcript').value!==s.edited)$('speech-transcript').value=s.edited;
  recordingText($('speech-original'),s.original);recordingText($('speech-status'),s.phase==='error'?'':s.message);
  $('speech-error').hidden=s.phase!=='error';recordingText($('speech-error'),s.phase==='error'?s.message:'');
  $('speech-confirm').disabled=active || !s.edited.trim();
}
speechTranscriber.subscribe(renderSpeechControls);browserRecorder.subscribe(renderSpeechControls);
$('speech-transcribe').addEventListener('click',()=>{if(speechEnabled)return speechTranscriber.transcribe(placementLearnerId);});
$('speech-cancel').addEventListener('click',()=>speechTranscriber.cancel());
$('speech-config-retry').addEventListener('click',loadSpeechConfiguration);
$('speech-transcript').addEventListener('input',()=>speechTranscriber.edit($('speech-transcript').value));
$('speech-confirm').addEventListener('click',()=>speechTranscriber.confirm(text=>{
  if(busy)return 'Wait for the Tutor to finish, then confirm again.';
  if($('message').value.trim() && $('message').value!==text)return 'Your message box already contains text. Clear it first, then confirm again.';
  $('message').value=text;$('message').dispatchEvent(new Event('input'));$('message').focus();return '';
}));
$('recording-card').addEventListener('toggle',()=>{if($('recording-card').open)loadSpeechConfiguration();else speechTranscriber.reset();});
window.addEventListener('hashchange',()=>speechTranscriber.reset());
window.addEventListener('pagehide',()=>speechTranscriber.reset());
document.addEventListener('learner-changed',()=>speechTranscriber.reset());
