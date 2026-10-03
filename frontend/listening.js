'use strict';

// Original short passages; answers are validated locally, never sent to a model.
const listeningExercises = Object.freeze([
  {id:'n5-time',level:'N5',text:'明日は九時に学校へ行きます。授業は九時半からです。',question:'When does the class start?',choices:['At 9:00','At 9:30','At 10:30'],answer:1,feedback:'九時半 means half past nine. Going to school and starting class happen at different times.'},
  {id:'n5-order',level:'N5',text:'パンを二つください。コーヒーは一つお願いします。',question:'How many pieces of bread does the speaker want?',choices:['One','Two','Three'],answer:1,feedback:'パンを二つ means two pieces of bread. 一つ refers to the coffee.'},
  {id:'n5-place',level:'N5',text:'本は机の上にあります。かばんは机の下にあります。',question:'Where is the bag?',choices:['On the desk','Beside the desk','Under the desk'],answer:2,feedback:'かばんは机の下にあります means the bag is under the desk. The book is on top.'},
  {id:'n5-day',level:'N5',text:'今日は月曜日です。水曜日に友達と映画を見ます。',question:'On which day will the speaker watch a movie?',choices:['Monday','Wednesday','Friday'],answer:1,feedback:'水曜日 is Wednesday. 月曜日 describes today, not the movie day.'},
  {id:'n4-rain',level:'N4',text:'雨が降っているので、今日は自転車に乗りません。バスで駅まで行きます。',question:'How will the speaker get to the station today?',choices:['By bicycle','By train','By bus'],answer:2,feedback:'バスで駅まで行きます means going to the station by bus. ので gives the reason: it is raining.'},
  {id:'n4-before',level:'N4',text:'買い物に行く前に、図書館で本を返します。それから、スーパーに行きます。',question:'What will the speaker do first?',choices:['Return a library book','Buy a book','Shop at the supermarket'],answer:0,feedback:'行く前に means before going. The speaker returns a book at the library before shopping.'},
  {id:'n4-request',level:'N4',text:'窓を開けてもいいですか。すみません、外が寒いので、開けないでください。',question:'What is the reply asking the first speaker to do?',choices:['Open the window','Keep the window closed','Go outside'],answer:1,feedback:'開けないでください means please do not open it. The reason is that it is cold outside.'},
  {id:'n4-change',level:'N4',text:'昨日は忙しくて、料理ができませんでした。今日は早く帰って、夕ご飯を作るつもりです。',question:'What does the speaker plan to do today?',choices:['Eat at a restaurant','Work late','Return home early and cook'],answer:2,feedback:'作るつもりです expresses an intention to cook. 昨日は describes yesterday, when the speaker could not cook.'}
].map(exercise => Object.freeze({...exercise,choices:Object.freeze(exercise.choices)})));
let listeningState = null, listeningPlayer = null;
function listeningCheck(exercise, choice) {
  if (!Number.isInteger(choice) || choice < 0 || choice >= exercise.choices.length) throw new Error('Choose one answer first.');
  return choice === exercise.answer;
}
function renderListening() {
  $('listening-intro').hidden = Boolean(listeningState);
  $('listening-exercise').hidden = !listeningState;
  $('listening-summary').hidden = true; $('listening-error').hidden = true;
  if (!listeningState) return;
  const state = listeningState, exercise = state.exercises[state.index];
  $('listening-heading').textContent = `${exercise.level} · Question ${state.index + 1} of ${state.exercises.length}`;
  $('listening-question').textContent = exercise.question;
  $('listening-transcript').textContent = ''; $('listening-transcript').hidden = true;
  $('listening-reveal').hidden = false;
  $('listening-feedback').textContent = ''; $('listening-next').hidden = true;
  $('listening-answer-form').hidden = false;
  $('listening-choices').replaceChildren(node('legend','Choose one answer'));
  exercise.choices.forEach((choice,index) => {
    const label = node('label',undefined,'jlpt-choice'), input = node('input'); input.type = 'radio'; input.name = 'listening-answer'; input.value = String(index); input.required = true;
    label.append(input,node('span',choice)); $('listening-choices').append(label);
  });
  listeningPlayer?.destroy(); $('listening-audio').replaceChildren();
  listeningPlayer = attachJapaneseAudio($('listening-audio'),exercise.text,'listening passage',() => { if (listeningState === state) state.heard = true; });
  $('listening-heading').focus();
}
$('listening-start').addEventListener('click', () => {
  japaneseAudio.stop(); listeningState = {exercises:listeningExercises.filter(e => e.level === $('listening-level').value),index:0,heard:false,assisted:false,answered:false,results:[]};
  if (!listeningState.exercises.length) { listeningState = null; return; }
  renderListening();
});
$('listening-reveal').addEventListener('click', () => {
  if (!listeningState || listeningState.answered) return;
  listeningState.assisted = true;
  $('listening-transcript').textContent = listeningState.exercises[listeningState.index].text;
  $('listening-transcript').hidden = false; $('listening-reveal').hidden = true;
  $('listening-feedback').textContent = 'Transcript revealed · this is assisted practice.';
});
$('listening-answer-form').addEventListener('submit', event => {
  event.preventDefault(); const state = listeningState; if (!state || state.answered) return;
  $('listening-error').hidden = true;
  try {
    if (!state.heard && !state.assisted) throw new Error('Play the passage first, or reveal the transcript for assisted practice.');
    const selected = $('listening-choices').querySelector('input:checked');
    if (!selected) throw new Error('Choose one answer first.');
    const exercise = state.exercises[state.index], correct = listeningCheck(exercise,Number(selected.value));
    state.answered = true; state.results.push({correct,assisted:state.assisted}); japaneseAudio.stop();
    $('listening-feedback').textContent = `${correct ? 'Correct.' : `Answer: ${exercise.choices[exercise.answer]}.`} ${exercise.feedback}${state.assisted ? ' · Assisted practice.' : ''}`;
    $('listening-transcript').textContent = exercise.text; $('listening-transcript').hidden = false; $('listening-reveal').hidden = true;
    $('listening-answer-form').hidden = true; $('listening-next').hidden = false;
    $('listening-next').textContent = state.index + 1 === state.exercises.length ? 'See practice summary' : 'Next question';
    $('listening-next').focus();
  } catch (error) { $('listening-error').textContent = error.message; $('listening-error').hidden = false; }
});
$('listening-next').addEventListener('click', () => {
  const state = listeningState; if (!state?.answered) return;
  japaneseAudio.stop();
  if (++state.index < state.exercises.length) { state.heard = false; state.assisted = false; state.answered = false; renderListening(); return; }
  const unassisted = state.results.filter(r => !r.assisted), assisted = state.results.filter(r => r.assisted);
  $('listening-exercise').hidden = true; $('listening-summary').hidden = false;
  $('listening-summary-text').textContent = `Listening without transcript: ${unassisted.filter(r => r.correct).length} correct of ${unassisted.length}. Assisted practice: ${assisted.filter(r => r.correct).length} correct of ${assisted.length}.`;
  $('listening-summary').focus(); listeningPlayer?.destroy(); listeningState = null;
});
$('listening-again').addEventListener('click', () => { listeningState = null; renderListening(); $('listening-level').focus(); });
$('listening-end').addEventListener('click', () => { japaneseAudio.stop(); listeningPlayer?.destroy(); listeningState = null; renderListening(); $('listening-level').focus(); });
document.addEventListener('learner-changed', () => { japaneseAudio.stop(); listeningPlayer?.destroy(); listeningState = null; renderListening(); });
