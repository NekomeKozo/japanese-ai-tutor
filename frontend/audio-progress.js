'use strict';

function prepareAudioAttempt(state, exercise) {
  state.audioAttempt={id:crypto.randomUUID(),exercise:exercise.id,owner:placementLearnerId,started:false,pending:null,completion:null};
  if(state.audioAttempt.owner) ensureAudioAttempt(state.audioAttempt).catch(()=>{});
}
async function ensureAudioAttempt(attempt) {
  if(attempt.started)return;
  if(!attempt.pending)attempt.pending=api(`/api/learners/${attempt.owner}/audio/attempts`,jsonOptions('POST',{
    attempt_id:attempt.id,exercise_id:attempt.exercise
  })).then(()=>{attempt.started=true;}).finally(()=>{attempt.pending=null;});
  await attempt.pending;
}
async function completeAudioAttempt(state, body) {
  const attempt=state.audioAttempt;
  if(!attempt?.owner || attempt.owner!==placementLearnerId)throw new Error('Choose your learner profile before saving practice.');
  if(attempt.result)return attempt.result;
  await ensureAudioAttempt(attempt);
  if(attempt.owner!==placementLearnerId)throw new Error('Your learner profile changed.');
  // Keep the first submitted answer across uncertain network failures.
  attempt.completion ||= body;
  attempt.result=await api(`/api/learners/${attempt.owner}/audio/attempts/${attempt.id}/complete`,jsonOptions('POST',attempt.completion));
  return attempt.result;
}
async function renderAudioProgress(id) {
  const panel=$('audio-progress');panel.replaceChildren(node('h2','Listening & speaking'),node('p','Loading audio practice…'));
  try {
    const data=await api(`/api/learners/${id}/audio/progress`);
    if(id!==placementLearnerId)return;
    panel.replaceChildren(node('h2','Listening & speaking'),node('p','Activity reflects practice, not pronunciation or proficiency.'));
    const total=data.listening.unassisted.completed+data.listening.assisted.completed;
    const completed=Object.values(data.speaking).reduce((sum,mode)=>sum+mode.completed,0);
    if(!data.listening.attempts && !Object.values(data.speaking).some(mode=>mode.attempts) && !data.voice.confirmed_turns){
      panel.append(node('p','Your listening and speaking progress will appear here after your first practice session.'));return;
    }
    const grid=node('div',undefined,'audio-progress-grid');
    const listening=node('section');listening.append(node('h3','Listening'),node('p',`Exercises completed: ${total} · Attempts: ${data.listening.attempts}`));
    for(const [key,label] of [['unassisted','Without transcript'],['assisted','Assisted']]){
      const metric=data.listening[key];listening.append(node('p',`${label}: ${metric.correct} correct / ${metric.completed} · Practice accuracy: ${metric.accuracy===null?'Not enough practice':metric.accuracy+'%'}`));
    }
    const speaking=node('section');speaking.append(node('h3','Speaking'),node('p',`Speaking exercises completed: ${completed}`));
    for(const [mode,label] of Object.entries(speakingModes)){const metric=data.speaking[mode];speaking.append(node('p',`${label}: ${metric.attempts} attempts · ${metric.completed} completed`));}
    const voice=node('section');voice.append(node('h3','Voice conversations'),node('p',`Completed conversations: ${data.voice.completed_conversations}`),node('p',`Confirmed spoken turns: ${data.voice.confirmed_turns}`));
    grid.append(listening,speaking,voice);panel.append(grid,node('h3','Recent audio practice'));
    const list=node('ul');
    for(const item of data.recent){
      let label=item.source==='listening'?`Listening · ${item.score===0?'Incorrect':'Correct'}${item.assisted?' · Assisted':''}`:
        item.source==='voice_conversation'?`${item.type==='voice_conversation_completed'?'Conversation finished':'Spoken reply saved'} · ${readable(item.scenario)}`:speakingModes[item.mode];
      list.append(node('li',`${dateLabel(item.created_at)} · ${label} · ${item.level}${item.id?' · '+item.id:''}`));
    }
    panel.append(list,node('p','Shows the latest 20 completed activities. Earlier untracked practice is not estimated.','small'));
  }catch(error){
    if(id!==placementLearnerId)return;
    panel.replaceChildren(node('h2','Listening & speaking'),node('p','Audio progress couldn’t load. Your other progress is still available.'));
    const retry=node('button','Retry audio progress','secondary');retry.type='button';retry.addEventListener('click',()=>renderAudioProgress(id));panel.append(retry);
  }
}
