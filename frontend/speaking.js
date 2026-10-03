'use strict';

// Original, fixed prompts. Reviewed for wording, level and conservative feedback.
// This catalog never generates exercises or writes proficiency evidence.
const speakingExercises=Object.freeze([
  {id:'beginner-read-hello',level:'Beginner',mode:'read',prompt:'こんにちは。',note:'A standard daytime greeting.'},
  {id:'beginner-read-thanks',level:'Beginner',mode:'read',prompt:'ありがとうございます。',note:'A polite way to say thank you.'},
  {id:'beginner-repeat-excuse',level:'Beginner',mode:'repeat',prompt:'すみません。',note:'Use this to get attention or apologize politely.'},
  {id:'beginner-repeat-request',level:'Beginner',mode:'repeat',prompt:'お願いします。',note:'A polite phrase to accompany a request.'},
  {id:'beginner-answer-name',level:'Beginner',mode:'answer',prompt:'お名前は何ですか？',sample:'ミゲルです。',kind:'name',note:'Name + です is a simple polite introduction. 私の名前は…です and …といいます are alternatives.'},
  {id:'beginner-answer-greeting',level:'Beginner',mode:'answer',prompt:'初めて会う人に、あいさつをしてください。',sample:'はじめまして。よろしくお願いします。',accepted:['はじめまして','はじめましてよろしくお願いします','初めまして','初めましてよろしくお願いします'],note:'はじめまして is used when meeting someone for the first time. You can add よろしくお願いします.'},
  {id:'n5-read-weather',level:'N5',mode:'read',prompt:'今日はいい天気ですね。',note:'ですね gently invites agreement about the weather.'},
  {id:'n5-read-school',level:'N5',mode:'read',prompt:'毎朝七時に学校へ行きます。',note:'に marks the time; へ marks the direction. 七時 can appear as しちじ in a transcript.'},
  {id:'n5-repeat-shop',level:'N5',mode:'repeat',prompt:'これを二つください。',note:'二つ is a general counter. を marks what you request.'},
  {id:'n5-repeat-order',level:'N5',mode:'repeat',prompt:'水をお願いします。',note:'A short polite request for water.'},
  {id:'n5-answer-count',level:'N5',mode:'answer',prompt:'りんごが二つあります。りんごはいくつありますか？',sample:'二つです。',accepted:['二つ','ふたつ','2つ','二つです','ふたつです','2つです','二個です','2個です','二つあります','りんごが二つあります','りんごは二つです','りんごは2つです'],note:'二つ／ふたつ means two. 二個 is another possible way to count apples.'},
  {id:'n5-answer-day',level:'N5',mode:'answer',prompt:'今日は月曜日です。今日は何曜日ですか？',sample:'月曜日です。',accepted:['月曜日','げつようび','月曜日です','げつようびです','今日は月曜日です','今日はげつようびです'],note:'月曜日／げつようび means Monday. 今日は is optional in this answer.'},
  {id:'n4-read-plan',level:'N4',mode:'read',prompt:'週末は友達と映画を見るつもりです。',note:'Verb dictionary form + つもりです expresses an intention.'},
  {id:'n4-read-reason',level:'N4',mode:'read',prompt:'雨が降っているので、バスで行きます。',note:'ので connects a reason to the action that follows.'},
  {id:'n4-repeat-permission',level:'N4',mode:'repeat',prompt:'ここで写真を撮ってもいいですか？',note:'て-form + もいいですか asks permission.'},
  {id:'n4-repeat-directions',level:'N4',mode:'repeat',prompt:'次の角を右に曲がってください。',note:'て-form + ください gives a polite instruction.'},
  {id:'n4-answer-yesterday',level:'N4',mode:'answer',prompt:'昨日、何をしましたか？',sample:'昨日は友達と映画を見ました。',kind:'past',note:'You can describe any real activity. A polite affirmative past answer often ends in ました; ませんでした is negative past.'},
  {id:'n4-answer-weekend',level:'N4',mode:'answer',prompt:'週末は何をするつもりですか？',sample:'友達と映画を見るつもりです。',kind:'plan',note:'Describe your own plan. Dictionary form + つもりです expresses an intention; 予定です is also used for plans.'}
].map(e=>Object.freeze({...e,accepted:e.accepted?Object.freeze(e.accepted):undefined})));
const speakingModes=Object.freeze({read:'Read Aloud',answer:'Spoken Answer',repeat:'Repeat a Phrase'});
function speakingNormalize(text) {return String(text).normalize('NFKC').replace(/[\s。、！？!?.,「」『』]/g,'');}
function speakingFeedback(exercise,text) {
  const normalized=speakingNormalize(text);
  if(exercise.mode!=='answer')return `${normalized===speakingNormalize(exercise.prompt)?'Your confirmed text matches the reference after spaces and punctuation are removed.':'Your confirmed text differs from the reference. Compare the two texts; kanji, kana and recognition choices can also cause differences.'} ${exercise.note} This is text comparison, not a pronunciation score.`;
  if(exercise.accepted?.some(answer=>speakingNormalize(answer)===normalized))return `Your confirmed text matches a reviewed answer for this prompt. ${exercise.note}`;
  if(exercise.kind==='name' && /^(?:私の名前は|わたしのなまえは|私は|わたしは)?[^はがをに。！？]{1,40}(?:です|といいます|と言います|と申します)$/.test(normalized))return `Your text uses a self-introduction pattern. Check that the name is transcribed correctly. ${exercise.note}`;
  if(exercise.kind==='past' && /(?:ました|ませんでした)$/.test(normalized))return `Your text uses a polite past ending that can fit this question. This does not check every word or your meaning. ${exercise.note}`;
  if(exercise.kind==='plan' && /(?:つもりです|予定です)$/.test(normalized))return `Your text uses a planning expression. Check the verb form against the example. ${exercise.note}`;
  return `A different expression may also be valid. This small practice set cannot judge your answer reliably, so it is not marked wrong. Compare the sample and check that the transcript reflects what you meant. ${exercise.note}`;
}
let speakingState=null,speakingPlayer=null,speakingVisible=false;
function speakingCurrent(){return speakingState?.exercises[speakingState.index];}
function clearSpeakingFeedback(){
  if(speakingState){speakingState.confirmed=null;speakingState.lastEvaluation=null;}
  $('speaking-feedback').hidden=true;$('speaking-confirmed').textContent='';$('speaking-reference').textContent='';$('speaking-feedback-text').textContent='';$('speaking-next').disabled=true;
}
function mountSpeakingRecorder(active) {
  const slot=active?$('speaking-recording-slot'):$('tutor-recording-slot');
  if($('recording-card').parentElement!==slot)slot.append($('recording-card'));
  setSpeechConfirmation(active?{apply:confirmSpeakingAnswer,success:'Confirmed text checked for this exercise. No Tutor message or mastery result was saved.'}:null);
  if(active)$('recording-card').hidden=false;
  if(active && !$('recording-card').open){$('recording-card').open=true;}
}
function renderSpeakingExercise() {
  const state=speakingState,exercise=speakingCurrent();$('speaking-exercise').hidden=!exercise;
  speakingPlayer?.destroy();speakingPlayer=null;
  if(!exercise)return;
  $('speaking-heading').textContent=`${exercise.level==='N4'?'Basic N4':exercise.level} · ${speakingModes[exercise.mode]} · ${state.index+1} of ${state.exercises.length}`;
  $('speaking-instruction').textContent={read:'Read this sentence aloud, then review and confirm your transcript.',answer:'Answer the question in Japanese. Review your transcript before confirming.',repeat:'Listen and repeat the phrase. If audio is unavailable, show the phrase for assisted practice.'}[exercise.mode];
  $('speaking-prompt').textContent=exercise.prompt;$('speaking-prompt').hidden=exercise.mode==='repeat' && !state.revealed;
  $('speaking-reveal').hidden=exercise.mode!=='repeat' || state.revealed;
  $('speaking-audio').replaceChildren();
  speakingPlayer=attachJapaneseAudio($('speaking-audio'),exercise.prompt,'speaking reference',()=>{if(speakingState===state)state.heard=true;});
  $('speaking-next').textContent=state.index+1===state.exercises.length?'Finish practice':'Next exercise';
  if(speakingVisible)mountSpeakingRecorder(true);
}
function speakingRoute(active) {
  speakingVisible=active;$('speaking-profile-note').hidden=Boolean(placementLearnerId);$('speaking-start').disabled=!placementLearnerId;
  if(!active){speakingPlayer?.destroy();speakingPlayer=null;clearSpeakingFeedback();mountSpeakingRecorder(false);return;}
  renderSpeakingExercise();
  if(!speakingState)mountSpeakingRecorder(false);
}
function startSpeakingPractice() {
  if(!placementLearnerId || busy || studyBusy)return;
  const exercises=speakingExercises.filter(e=>e.level===$('speaking-level').value && e.mode===$('speaking-mode').value);
  if(!exercises.length)return;
  japaneseAudio.stop();browserRecorder.cancel('');speechTranscriber.reset();
  speakingState={exercises,index:0,heard:false,revealed:false,confirmed:null,lastEvaluation:null};
  clearSpeakingFeedback();$('speaking-notice').textContent='Review/edit the transcript and explicitly confirm each answer.';
  renderSpeakingExercise();$('speaking-heading').focus();
}
function confirmSpeakingAnswer(text) {
  const state=speakingState,exercise=speakingCurrent();
  if(!speakingVisible || !exercise || browserRecorder.state().phase!=='preview')return 'Open the speaking exercise and transcribe your recording first.';
  if(exercise.mode==='repeat' && !state.heard && !state.revealed)return 'Listen to the reference first, or show the phrase for assisted practice.';
  const feedback=state.lastEvaluation?.text===text?state.lastEvaluation.feedback:speakingFeedback(exercise,text);
  state.lastEvaluation={text,feedback};state.confirmed={original:speechTranscriber.state().original,text,reference:exercise.sample || exercise.prompt,feedback};
  $('speaking-confirmed').textContent=text;$('speaking-reference').textContent=state.confirmed.reference;
  $('speaking-reference-label').textContent=exercise.mode==='answer'?'One possible answer':'Reference text';
  $('speaking-feedback-text').textContent=feedback;$('speaking-feedback').hidden=false;$('speaking-next').disabled=false;
  if(exercise.mode==='repeat'){$('speaking-prompt').hidden=false;}
  return '';
}
$('speaking-start').addEventListener('click',startSpeakingPractice);
$('speaking-reveal').addEventListener('click',()=>{if(!speakingState)return;speakingState.revealed=true;$('speaking-prompt').hidden=false;$('speaking-reveal').hidden=true;});
$('speaking-retry').addEventListener('click',()=>{japaneseAudio.stop();browserRecorder.cancel('Ready to retry this exercise.');speechTranscriber.reset();clearSpeakingFeedback();});
function endSpeakingPractice(note='Speaking practice ended. Choose another set when ready.') {
  japaneseAudio.stop();browserRecorder.cancel('');speechTranscriber.reset();speakingPlayer?.destroy();speakingPlayer=null;
  clearSpeakingFeedback();speakingState=null;$('speaking-exercise').hidden=true;mountSpeakingRecorder(false);$('speaking-notice').textContent=note;
}
$('speaking-end').addEventListener('click',()=>endSpeakingPractice());
$('speaking-next').addEventListener('click',()=>{
  if(!speakingState?.confirmed)return;
  if(speakingState.index+1===speakingState.exercises.length){endSpeakingPractice('This speaking set is finished. No pronunciation score or mastery result was saved.');return;}
  japaneseAudio.stop();browserRecorder.cancel('');speechTranscriber.reset();
  ++speakingState.index;speakingState.heard=false;speakingState.revealed=false;clearSpeakingFeedback();renderSpeakingExercise();$('speaking-heading').focus();
});
speechTranscriber.subscribe(s=>{
  if(speakingState?.confirmed && s.edited.trim()!==speakingState.confirmed.text){speakingState.confirmed=null;$('speaking-feedback').hidden=true;$('speaking-next').disabled=true;}
});
browserRecorder.subscribe(s=>{if(speakingState?.confirmed && s.phase!=='preview')clearSpeakingFeedback();});
window.addEventListener('pagehide',()=>endSpeakingPractice(''));
document.addEventListener('learner-changed',()=>endSpeakingPractice(''));
