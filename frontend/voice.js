'use strict';

// Voice is a transient input method for the existing persistent conversation.
let voiceReplyTarget=null,voiceSendTask=null,confirmedVoiceDraft=null;
function voiceTranscriptionFor(message){return sameVoiceTarget(voiceReplyTarget) && confirmedVoiceDraft?.text===message?confirmedVoiceDraft.transcription:null;}
function activeVoiceConversation() {
  return !$('tutor-panel').hidden && practiceState?.status==='active' && savedSession &&
    sessionId===practiceState.session_id && Boolean(placementLearnerId);
}
function sameVoiceTarget(target) {
  return target && activeVoiceConversation() && target.session===sessionId && target.learner===placementLearnerId;
}
function clearVoiceReply() {
  voiceReplyTarget=null;confirmedVoiceDraft=null;
  browserRecorder.cancel('');speechTranscriber.reset();
}
function voicePracticeChanged(state) {
  if(practiceState?.session_id!==state?.session_id || practiceState?.status!==state?.status ||
    (voiceReplyTarget && (state?.status!=='active' || state.session_id!==voiceReplyTarget.session)))clearVoiceReply();
  if(state?.status==='completed'){japaneseAudio.stop();browserRecorder.cancel('');speechTranscriber.reset();}
}
function voiceRecordingAllowed() {
  if(!activeVoiceConversation())return $('tutor-panel').hidden || practiceState?.status!=='completed';
  if(busy){$('voice-reply-notice').textContent='Wait for the current reply before recording.';return false;}
  confirmedVoiceDraft=null;voiceReplyTarget={learner:placementLearnerId,session:sessionId};return true;
}
function voiceReplyControls() {
  const active=activeVoiceConversation(),inTutor=!$('tutor-panel').hidden;
  $('voice-reply-notice').hidden=$('voice-reply-cancel').hidden=!active;
  if(inTutor){
    $('recording-card').hidden=practiceState?.status==='completed';
    $('recording-summary').textContent=active?'Record spoken reply':'Record spoken Japanese';
    setSpeechConfirmation(active?{apply:confirmVoiceReply,label:'Confirm and Send',
      help:'Review recognition mistakes before sending. Confirm and Send submits only your edited Japanese text to this active conversation.',
      success:'Sending your confirmed text to the conversation…'}:null);
  }else if(!speakingVisible){setSpeechConfirmation(null);}
  if(active){
    const r=browserRecorder.state();
    $('recording-start').textContent=r.phase==='preview'?'Record again':'Record Reply';
    $('recording-start').disabled=busy || r.availability!=='supported' || r.permissionPending || ['requesting','recording','processing'].includes(r.phase);
    $('speech-confirm').disabled=busy || speechTranscriber.state().confirming || !speechTranscriber.state().edited.trim() || ['preparing','uploading'].includes(speechTranscriber.state().phase);
  }
}
function voiceChatSucceeded() {
  if(voiceReplyTarget){clearVoiceReply();$('voice-reply-notice').textContent='Confirmed reply sent. Type or record your next reply.';}
}
function confirmVoiceReply(text) {
  if(busy)return 'Wait for the current reply before sending again.';
  const target=voiceReplyTarget;
  if(!sameVoiceTarget(target) || browserRecorder.state().phase!=='preview')return 'This recording no longer belongs to the active conversation. Record your reply again.';
  if($('message').value.trim() && $('message').value.trim()!==text)return 'Your text editor already contains a different reply. Send or clear it before confirming this recording.';
  if(!speechTranscriber.state().requestId)return 'Transcribe your reply successfully before sending.';
  confirmedVoiceDraft={text,transcription:speechTranscriber.state().requestId};
  $('message').value=text;updateCount();
  // submitChatMessage sets busy synchronously and reuses pendingChat.request_id.
  // Failed generation retains this transcript and the editor for an explicit retry.
  voiceSendTask=submitChatMessage().then(ok=>{
    if(!ok && voiceReplyTarget===target){$('voice-reply-notice').textContent='Your confirmed text is still in the editor. Retry Send message or Confirm and Send; no new transcription is needed.';}
    voiceReplyControls();return ok;
  });
  return '';
}
$('voice-reply-cancel').addEventListener('click',()=>{clearVoiceReply();$('voice-reply-notice').textContent='Voice reply cancelled. Your typed draft and conversation are unchanged.';voiceReplyControls();});
browserRecorder.subscribe(voiceReplyControls);speechTranscriber.subscribe(voiceReplyControls);
window.addEventListener('hashchange',()=>{voiceReplyTarget=null;confirmedVoiceDraft=null;});
window.addEventListener('pagehide',()=>{voiceReplyTarget=null;confirmedVoiceDraft=null;});
document.addEventListener('learner-changed',()=>{voiceReplyTarget=null;confirmedVoiceDraft=null;});
