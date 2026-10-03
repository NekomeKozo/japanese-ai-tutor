const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const root = path.join(__dirname, '..', 'frontend');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const scripts = [...html.matchAll(/src="\/static\/([^\"]+\.js)"/g)].map(m => m[1]);
function harness(audio = {}) {
  const elements = new Map(); const requests = []; const storage = new Map();
  class Element {
    constructor(tag = 'div') { this.tagName=tag; this.children=[]; this.listeners={}; this.hidden=false; this.value=''; this.textContent=''; this.attributes={}; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children=children; this.textContent=''; }
    cloneNode() { return new Element(this.tagName); }
    get firstElementChild() { return this.children[0] || new Element(); }
    get childElementCount() { return this.children.length; }
    setAttribute(k,v) { this.attributes[k]=v; }
    removeAttribute(k) { delete this.attributes[k]; if(k==='src')this.src=''; }
    pause() { this.paused=true; }
    play() { this.paused=false; return Promise.resolve(); }
    load() { this.loaded=true; }
    addEventListener(type, fn) { this.listeners[type]=fn; }
    querySelectorAll() { return []; }
    querySelector() { return this.selected || null; }
    closest() { return null; }
    focus() { this.focused=true; }
  }
  for (const m of html.matchAll(/<([\w-]+)\b[^>]*\bid="([^"]+)"[^>]*>/g)) { const e=new Element(m[1]); e.hidden=/\bhidden\b/.test(m[0]); elements.set(m[2],e); }
  elements.get('review-minutes').value='10'; elements.get('onboarding-goal-select').value='general';
  const windowEvents = {}, documentEvents = {};
  const ctx = vm.createContext({console, Event, URLSearchParams, Intl, TypeError, SyntaxError, setInterval:()=>1, clearInterval(){}, setTimeout:()=>1, clearTimeout(){}, crypto:require('node:crypto').webcrypto,
    document:{getElementById:id=>elements.get(id),createElement:tag=>new Element(tag),querySelectorAll:()=>[],querySelector:selector=>selector==='.skip-link'?new Element('a'):null,addEventListener(type,fn){(documentEvents[type] ||= []).push(fn);},dispatchEvent(event){for(const fn of documentEvents[event.type] || []) fn(event);}},
    window:{...audio,addEventListener(type,fn){(windowEvents[type] ||= []).push(fn);},location:{assign(url){ctx.redirect=url;}}},location:{hash:''},navigator:{onLine:true,mediaDevices:audio.mediaDevices},performance:{now:audio.now || (()=>0)},
    localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    sessionStorage:{getItem:()=>null,setItem(){}},
    fetch:async (url, options={})=>{ requests.push({url,...options}); throw new TypeError('offline'); }
  });
  // Run all real scripts; bootstrap is invoked explicitly by each test.
  for (const name of scripts) { let source=fs.readFileSync(path.join(root,name),'utf8'); if(name==='shell.js') source=source.replace(/boot\(\);\s*$/, ''); vm.runInContext(source,ctx,{filename:name}); }
  return {ctx,elements,requests,storage,windowEvents,documentEvents,run:source=>vm.runInContext(source,ctx)};
}

test('unique DOM IDs and all literal JavaScript ID references resolve',()=>{
  const ids=[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]); assert.equal(new Set(ids).size,ids.length);
  for (const name of scripts) for (const match of fs.readFileSync(path.join(root,name),'utf8').matchAll(/\$\('([^']+)'\)/g)) assert.ok(ids.includes(match[1]),`${name}: ${match[1]}`);
});
test('new Home boots without a model call or creation of a session',async()=>{
  const h=harness(); await h.run('boot()'); assert.equal(h.requests.length,0); assert.equal(h.elements.get('home-content').hidden,false); assert.equal(h.elements.get('home-action').textContent,'Find my starting point');
});
test('next action uses placement, saved study, due reviews, then planning',()=>{
  const h=harness(); for(const [state,expected] of [[{},'placement'],[{learner:{},assessment:{status:'in_progress'}},'placement'],[{learner:{},active:{status:'in_progress'},due:5},'continue'],[{learner:{},due:5},'review'],[{learner:{},due:0},'study']]) { h.ctx.state=state; assert.equal(h.run('chooseNextAction(state)'),expected); }
});
test('unknown hashes safely show Home, and Progress subnavigation is explicit',()=>{
  const h=harness(); h.ctx.location.hash='#unknown'; assert.equal(h.run('currentRoute().section'),'home'); h.run("progressSection('knowledge')"); assert.equal(h.elements.get('progress-knowledge').hidden,false); assert.equal(h.elements.get('profile-evidence').hidden,true);
});
test('failed restoration keeps content hidden and exposes retry',async()=>{
  const h=harness(); h.storage.set('japanese-tutor-learner','example'); await h.run('boot()'); assert.equal(h.elements.get('app-error').hidden,false); assert.equal(h.elements.get('home-content').hidden,true); assert.equal(h.elements.get('app-loading').hidden,true);
});
test('navigation to an active study retains the activity and answer draft',async()=>{
  const h=harness(); h.run("placementLearnerId='example'; studyPlan={session_id:'saved',status:'in_progress',activities:[],estimated_minutes:5,note:''}; studyActivity={activity_id:'current'}; refreshReviews=async()=>{};"); h.elements.get('study-answer').value='先生です。'; h.elements.get('study-activity').hidden=false; await h.run('loadStudy()'); assert.equal(h.elements.get('study-answer').value,'先生です。'); assert.equal(h.elements.get('study-activity').hidden,false); assert.equal(h.requests.length,0);
});
test('dirty settings survive navigation without a refetch',async()=>{
  const h=harness(); h.run("placementLearnerId='example'; settingsLearner='example'; settingsDirty=true;"); h.elements.get('pref-goal').value='travel'; await h.run('loadSettings()'); assert.equal(h.elements.get('pref-goal').value,'travel'); assert.equal(h.requests.length,0);
});
test('HTTP 401 redirects to the access gate; provider details get friendly copy',async()=>{
  const h=harness(); h.ctx.fetch=async()=>({status:401}); await assert.rejects(h.run("api('/api/health')"),/Sign in/); assert.equal(h.ctx.redirect,'/access'); assert.match(h.run("friendlyError({message:'Check model configuration',code:'provider_error'})"),/tutor couldn’t answer/);
});
test('placement drafts are not reset by ordinary panel navigation',async()=>{
  const h=harness(); h.run("appReady=true; assessmentState={status:'in_progress'}"); h.ctx.location.hash='#placement'; h.elements.get('assessment-answer').value='日本語'; await h.run('renderRoute()'); assert.equal(h.elements.get('assessment-answer').value,'日本語'); assert.equal(h.requests.length,0);
});
test('tutor draft is retained when navigating away and back',async()=>{
  const h=harness(); h.run("appReady=true; sessionId='saved'"); h.elements.get('message').value='日本に行きたいです。'; h.ctx.location.hash='#placement'; await h.run('renderRoute()'); h.ctx.location.hash='#tutor'; await h.run('renderRoute()'); assert.equal(h.elements.get('message').value,'日本に行きたいです。'); assert.equal(h.requests.length,0);
});

test('saved Home reads existing summaries without any mutation or AI route',async()=>{
  const h=harness(); h.run("placementLearnerId='learner'");
  h.ctx.fetch=async url=>{h.requests.push({url}); const data=url.endsWith('/profile')?{estimated_level:'Beginner',preferences:{primary_goal:'travel'},weak_topics:[]}:url.includes('/reviews/due')?{due_count:0}:url.endsWith('/active')?null:[];return {ok:true,status:200,json:async()=>data};};
  await h.run('renderHome()'); assert.equal(h.requests.length,4); assert.ok(h.requests.every(r=>r.url.startsWith('/api/learners/learner/')&&!r.method)); assert.equal(h.elements.get('home-action').textContent,'Plan today’s study');
});
test('failed chat keeps the draft and retries with the same request ID',async()=>{
  const h=harness(); h.run("sessionId='session'; placementLearnerId='learner'; savedSession=true;");
  h.elements.get('message').value='日本を行きたいです。'; h.elements.get('mode').value='correct'; h.elements.get('level').value='beginner';
  let attempts=0; h.ctx.fetch=async(url,opts)=>{h.requests.push({url,...opts}); if(!attempts++)throw new TypeError('offline');return {ok:true,status:200,json:async()=>({response:{message:'Try に.',examples:[],exercise:null}})};};
  const submit=h.elements.get('chat-form').listeners.submit;
  await submit({preventDefault(){}}); assert.equal(h.elements.get('message').value,'日本を行きたいです。');
  await submit({preventDefault(){}}); assert.equal(h.elements.get('message').value,''); assert.equal(JSON.parse(h.requests[0].body).request_id,JSON.parse(h.requests[1].body).request_id);
});
test('failed dashboard request never presents empty data as a loaded summary',async()=>{
  const h=harness(); h.run("placementLearnerId='learner'"); await assert.rejects(h.run('renderHome()')); assert.equal(h.elements.get('home-content').hidden,true); assert.equal(h.elements.get('home-loading').hidden,true);
});

test('restoring a learner does not load or create a tutor conversation until Tutor is opened',async()=>{
  const h=harness(); h.ctx.fetch=async(url,opts={})=>{h.requests.push({url,...opts});return {ok:true,status:200,json:async()=>({learner_id:'learner',estimated_level:'Beginner',preferences:{}})};};
  await h.run("activateLearner('learner')"); assert.equal(h.requests.length,1); assert.ok(h.requests[0].url.endsWith('/profile')); assert.equal(h.run('sessionId'),null);
});


test('an active study error remains visible after navigating away and back',async()=>{
  const h=harness(); h.run("placementLearnerId='learner'; studyPlan={session_id:'saved',status:'in_progress',activities:[],estimated_minutes:5,note:''}; refreshReviews=async()=>{};");
  h.elements.get('study-error').hidden=false; h.elements.get('study-error').textContent='Please retry this lesson.';
  await h.run('loadStudy()'); assert.equal(h.elements.get('study-error').hidden,false); assert.equal(h.elements.get('study-error').textContent,'Please retry this lesson.');
});

const practice = {session_id:'practice',learner_id:'learner',status:'active',effective_level:'N5',correction_policy:'balanced',scenario:{key:'restaurant',title:'At a restaurant',description:'Order a meal.',goal:'Order food and a drink.',opening_line:'何名様ですか？',minimum_level:'N5'}};
const practiceSaved = {session_id:'practice',learner_id:'learner',conversation:practice,turns:[],interaction_count:0,ended_at:null};
function respond(h, handler) {
  h.ctx.fetch=async(url,options={})=>{h.requests.push({url,...options});return {ok:true,status:200,json:async()=>handler(url,options)};};
}
test('scenario setup loads authored data once without generation',async()=>{
  const h=harness();h.run("placementLearnerId='learner'");respond(h,()=>[practice.scenario]);
  await h.run('loadScenarioCatalog()');await h.run('loadScenarioCatalog()');
  assert.equal(h.requests.length,1);assert.equal(h.requests[0].url,'/api/conversation/scenarios');
  assert.equal(h.elements.get('practice-start').disabled,false);
  assert.match(h.elements.get('practice-description').textContent,/Order a meal/);
});
test('saved roleplay restoration uses the existing transcript and one opening',async()=>{
  const h=harness();h.run("placementLearnerId='learner'");respond(h,url=>url.endsWith('/active')?practice:practiceSaved);
  await h.run('restoreActivePractice()');await h.run("openSavedSession('practice')");
  assert.equal(h.run('sessionId'),'practice');assert.equal(h.elements.get('conversation').children.length,1);
  assert.equal(h.elements.get('practice-active').hidden,false);assert.equal(h.elements.get('mode').hidden,true);
  assert.equal(h.elements.get('practice-goal').textContent,practice.scenario.goal);
  assert.ok(h.requests.every(r=>!r.method));
});
test('active roleplay cannot be silently closed by general reset',async()=>{
  const h=harness();h.ctx.practice=practice;h.run("placementLearnerId='learner';sessionId='practice';applyPractice(practice)");
  await h.run('resetSession()');assert.equal(h.requests.length,0);assert.equal(h.run('sessionId'),'practice');
  assert.match(h.elements.get('error').textContent,/Finish/);
});
test('practice start uses an authored opening without a chat request',async()=>{
  const h=harness();h.run("placementLearnerId='learner'");h.elements.get('practice-scenario').value='restaurant';h.elements.get('practice-policy').value='balanced';
  respond(h,url=>url.endsWith('/conversations')?practice:practiceSaved);
  await h.elements.get('practice-start').listeners.click();
  assert.equal(h.requests.length,2);assert.ok(h.requests.every(r=>r.url!='/api/chat'));
  assert.equal(h.run('practiceState.status'),'active');assert.equal(h.run('sessionId'),'practice');
});
test('uncertain start retry restores the already-created active conversation',async()=>{
  const h=harness();h.run("placementLearnerId='learner'");
  h.ctx.fetch=async(url,options={})=>{h.requests.push({url,...options});return url.endsWith('/conversations')?{ok:false,status:409,json:async()=>({error:{code:'conversation_active',message:'Resume first'}})}:{ok:true,status:200,json:async()=>url.endsWith('/active')?practice:practiceSaved};};
  await h.elements.get('practice-start').listeners.click();assert.equal(h.run('sessionId'),'practice');
  assert.equal(h.elements.get('practice-error').hidden,true);
});
test('finish renders stored recap and leaves transcript available',async()=>{
  const h=harness();h.ctx.practice=practice;h.run("placementLearnerId='learner';sessionId='practice';applyPractice(practice)");
  const finished={...practice,status:'completed',recap:{turn_count:3,final_effective_level:'N5',topics:['Particles'],observations:3,scored_turns:3,recent_performance_average:.7}};
  respond(h,()=>finished);await h.elements.get('practice-finish').listeners.click();
  assert.equal(h.requests.length,1);assert.ok(h.requests[0].url.endsWith('/finish'));
  assert.equal(h.elements.get('practice-recap').hidden,false);assert.equal(h.elements.get('chat-form').hidden,true);
  assert.equal(h.run('sessionId'),'practice');assert.equal(h.elements.get('practice-active').hidden,true);
});
test('roleplay navigation retains state and draft without a new conversation',async()=>{
  const h=harness();h.ctx.practice=practice;h.run("appReady=true;placementLearnerId='learner';sessionId='practice';scenarioCatalog=[practice.scenario];applyPractice(practice)");
  h.elements.get('message').value='水をください。';h.ctx.location.hash='#placement';await h.run('renderRoute()');h.ctx.location.hash='#tutor';await h.run('renderRoute()');
  assert.equal(h.elements.get('message').value,'水をください。');assert.equal(h.run('practiceState.status'),'active');assert.equal(h.requests.length,0);
});

const jlptFixture = {session_id:'jlpt-saved',level:'N5',mode:'quick',status:'in_progress',question_count:5,answered_count:0,remaining_seconds:null,
  question:{id:'jlpt_n5_kanji_01',section:'kanji',prompt:'Read 一 in 一つ.',choices:[],passage_text:null},feedback:null,result:null,review:[]};
test('JLPT route restores lazily and preserves the answer draft on navigation',async()=>{
  const h=harness();h.run("appReady=true;placementLearnerId='learner'");
  respond(h,url=>url.endsWith('/catalog')?{}:url.endsWith('/history')?[]:jlptFixture);
  h.ctx.location.hash='#study/jlpt';await h.run('renderRoute()');
  assert.equal(h.requests.length,3);assert.equal(h.elements.get('personalized-study').hidden,true);
  assert.equal(h.elements.get('jlpt-panel').hidden,false);
  h.elements.get('jlpt-answer').value='ひと';h.ctx.location.hash='#placement';await h.run('renderRoute()');
  h.ctx.location.hash='#study/jlpt';await h.run('renderRoute()');
  assert.equal(h.elements.get('jlpt-answer').value,'ひと');assert.equal(h.requests.length,3);
  assert.ok(h.requests.every(r=>!r.method && r.url!='/api/chat'));
});
test('JLPT network retry preserves answer and submission identity',async()=>{
  const h=harness();h.ctx.fixture=jlptFixture;h.run("placementLearnerId='learner';jlptAccept(fixture)");
  h.elements.get('jlpt-answer').value='ひと';
  const submit=h.elements.get('jlpt-answer-form').listeners.submit;
  await submit({preventDefault(){}});await submit({preventDefault(){}});
  assert.equal(h.elements.get('jlpt-answer').value,'ひと');assert.equal(h.elements.get('jlpt-error').hidden,false);
  assert.equal(h.requests.length,2);assert.equal(JSON.parse(h.requests[0].body).submission_id,JSON.parse(h.requests[1].body).submission_id);
});

test('expired mock restoration refreshes history after completion and clears retry',async()=>{
  const h=harness();h.run("placementLearnerId='learner'");h.elements.get('jlpt-retry').hidden=false;
  let historyReads=0;
  const finished={...jlptFixture,mode:'mock',status:'completed',question:null,elapsed_seconds:1500,
    result:{correct:1,total:20,accuracy:5,answered:1,note:'Practice only',sections:{},done_well:[],needs_review:[]}};
  respond(h,url=>url.endsWith('/catalog')?{}:url.endsWith('/active')?finished:
    [{level:'N4',mode:'mock',status:++historyReads===1?'in_progress':'completed',accuracy:historyReads===1?null:5}]);
  await h.run('loadJLPT()');
  const row=h.elements.get('jlpt-history').children[0];
  assert.match(row.children[0].textContent,/completed.*5%/);
  assert.equal(row.children[1].textContent,'Open');
  assert.equal(h.elements.get('jlpt-retry').hidden,true);
  assert.equal(h.elements.get('jlpt-results').hidden,false);
});
test('JLPT successful answer shows feedback then advances without another API call',async()=>{
  const h=harness();h.ctx.fixture=jlptFixture;h.run("placementLearnerId='learner';jlptAccept(fixture)");
  const feedback={...jlptFixture.question,answer:'ひと',correct:true,correct_answers:['ひと'],explanation:'一つ is ひとつ.'};
  respond(h,()=>({...jlptFixture,answered_count:1,question:{...jlptFixture.question,id:'jlpt_n5_kanji_02'},feedback}));
  h.elements.get('jlpt-answer').value='ひと';await h.elements.get('jlpt-answer-form').listeners.submit({preventDefault(){}});
  assert.equal(h.elements.get('jlpt-feedback').hidden,false);assert.equal(h.elements.get('jlpt-answer-form').hidden,true);
  h.elements.get('jlpt-next').listeners.click();
  assert.equal(h.elements.get('jlpt-answer-form').hidden,false);assert.equal(h.elements.get('jlpt-answer').value,'');assert.equal(h.requests.length,1);
});
test('mock UI shows no feedback before finish and uses server remaining time',()=>{
  const h=harness();h.ctx.fixture={...jlptFixture,mode:'mock',remaining_seconds:180};
  h.run("placementLearnerId='learner';jlptAccept(fixture)");
  assert.equal(h.elements.get('jlpt-feedback').hidden,true);assert.equal(h.elements.get('jlpt-submit').textContent,'Save answer');
  assert.match(h.elements.get('jlpt-timer').textContent,/3:00/);assert.equal(h.requests.length,0);
});
test('JLPT start retries use the same request and no provider path',async()=>{
  const h=harness();h.run("placementLearnerId='learner'");
  h.elements.get('jlpt-level').value='N5';h.elements.get('jlpt-mode').value='quick';h.elements.get('jlpt-section').value='mixed';
  const submit=h.elements.get('jlpt-setup').listeners.submit;
  await submit({preventDefault(){}});await submit({preventDefault(){}});
  assert.equal(JSON.parse(h.requests[0].body).request_id,JSON.parse(h.requests[1].body).request_id);
  assert.ok(h.requests.every(r=>r.url.endsWith('/jlpt/sessions')));
});
test('JLPT stale restore cannot display another learner’s session',async()=>{
  const h=harness();h.run("placementLearnerId='first'");let release;
  h.ctx.fetch=async url=>({ok:true,status:200,json:async()=>url.endsWith('/active')?await new Promise(resolve=>{release=resolve;}):[]});
  const pending=h.run('loadJLPT()');await new Promise(resolve=>setImmediate(resolve));
  h.run("placementLearnerId='second'");release(jlptFixture);await pending;
  assert.equal(h.run('jlptState'),null);
});
test('JLPT follow-up initializes Tutor before filling its composer and preserves existing drafts',async()=>{
  const h=harness();h.ctx.fixture={...jlptFixture.question,correct_answers:['ひと'],explanation:'One in this counter.'};
  h.run("placementLearnerId='learner';jlptState={session_id:'jlpt-saved'};ensureTutorSession=async()=>{sessionId='tutor';$('message').value='';}");
  respond(h,()=>h.ctx.fixture);await h.run('jlptAsk(fixture)');
  assert.match(h.elements.get('message').value,/Please explain/);assert.equal(h.ctx.location.hash,'tutor');
  const draft=h.elements.get('message').value;await h.run('jlptAsk(fixture)');
  assert.equal(h.elements.get('message').value,draft);assert.equal(h.requests.length,1);
  assert.match(h.elements.get('jlpt-error').textContent,/draft is still saved/);
});

function speechMock(voices = [{name:'Japanese local',voiceURI:'ja-local',lang:'ja-JP',localService:true}]) {
  const spoken = [], events = new Map();
  const synth = {voices,cancels:0,getVoices(){return this.voices;},cancel(){this.cancels++;},speak(utterance){spoken.push(utterance);},
    addEventListener(name,fn){events.set(name,fn);},removeEventListener(name){events.delete(name);}};
  class Utterance { constructor(text){this.text=text;} }
  return {synth,Utterance,spoken,events,h:harness({speechSynthesis:synth,SpeechSynthesisUtterance:Utterance})};
}
test('audio discovers Japanese voices and prefers local voices without auto-speaking',()=>{
  const m=speechMock([{name:'English',lang:'en-US'},{name:'Remote JP',lang:'ja-JP',localService:false},{name:'Local JP',lang:'ja-JP',localService:true}]);
  const state=m.h.run('japaneseAudio.state()');assert.equal(state.availability,'ready');assert.equal(state.voices.length,2);assert.match(state.selected,/Local JP/);assert.equal(m.spoken.length,0);
});
test('late voiceschanged recovers the loading player without using an English voice',()=>{
  const m=speechMock([{name:'English',lang:'en-US'}]);assert.equal(m.h.run("japaneseAudio.play('こんにちは','test')"),false);assert.equal(m.spoken.length,0);
  m.synth.voices=[{name:'Japanese',lang:'ja_JP'}];m.events.get('voiceschanged')();
  assert.equal(m.h.run('japaneseAudio.state().availability'),'ready');assert.equal(m.spoken.length,0);
  m.h.run("japaneseAudio.play('こんにちは','test')");assert.equal(m.spoken[0].voice.lang,'ja_JP');
});
test('missing Japanese voice settles into a helpful state; unsupported browser is safe',()=>{
  const m=speechMock([]);const timers=new Map();let seq=0;
  m.h.ctx.deps={synth:m.synth,Utterance:m.Utterance,schedule(fn){timers.set(++seq,fn);return seq;},unschedule(id){timers.delete(id);}};
  const audio=m.h.run('createJapaneseAudio(deps)');assert.equal(audio.state().availability,'loading');timers.get(1)();
  assert.equal(audio.state().availability,'missing');assert.equal(audio.play('日本語','x'),false);assert.equal(m.spoken.length,0);
  assert.equal(harness().run('japaneseAudio.state().availability'),'unsupported');
});
test('play, finish, replay and stop keep a single queue and ignore cancelled callbacks',()=>{
  const m=speechMock();m.h.run("japaneseAudio.play('こんにちは！','one')");const first=m.spoken[0];const staleStart=first.onstart,staleEnd=first.onend;
  first.onstart();assert.equal(m.h.run('japaneseAudio.state().phase'),'playing');
  m.h.run("japaneseAudio.play('こんばんは！','two')");assert.equal(first.onend,null);staleStart();staleEnd();
  assert.equal(m.h.run('japaneseAudio.state().owner'),'two');assert.equal(m.spoken.length,2);
  m.spoken[1].onstart();m.spoken[1].onend();assert.equal(m.h.run('japaneseAudio.state().phase'),'idle');
  m.h.run("japaneseAudio.play('こんばんは！','two');japaneseAudio.stop()");assert.equal(m.spoken.length,3);assert.equal(m.h.run('japaneseAudio.state().owner'),null);
});
test('all three speeds and voice selection apply to the next utterance',()=>{
  const m=speechMock([{name:'JP one',lang:'ja-JP'},{name:'JP two',lang:'ja-JP'}]);
  for(const rate of [.75,1,1.25]){m.h.ctx.rate=rate;m.h.run("japaneseAudio.setRate(rate);japaneseAudio.play('日本語','one')");assert.equal(m.spoken.at(-1).rate,rate);}
  const id=m.h.run('japaneseAudio.state().voices[1].id');m.h.ctx.voiceId=id;m.h.run("japaneseAudio.setVoice(voiceId);japaneseAudio.play('日本語','one')");assert.equal(m.spoken.at(-1).voice.name,'JP two');
  m.h.run('japaneseAudio.setRate(100)');assert.equal(m.h.run('japaneseAudio.state().rate'),1.25);
});
test('synthesis failure, thrown engines and silent-start timeouts recover for retry',()=>{
  const m=speechMock();m.h.run("japaneseAudio.play('日本語','one')");m.spoken.at(-1).onerror({error:'synthesis-failed'});
  assert.equal(m.h.run('japaneseAudio.state().phase'),'error');assert.match(m.h.run('japaneseAudio.state().message'),/could not play/);
  m.synth.speak=()=>{throw Error('engine failure');};assert.equal(m.h.run("japaneseAudio.play('日本語','one')"),false);
  const timers=new Map();let seq=0;m.synth.speak=u=>m.spoken.push(u);
  m.h.ctx.deps={synth:m.synth,Utterance:m.Utterance,schedule(fn,ms){timers.set(++seq,{fn,ms});return seq;},unschedule(id){timers.delete(id);}};
  const audio=m.h.run('createJapaneseAudio(deps)');audio.play('日本語','test');[...timers.values()].find(t=>t.ms===10000).fn();assert.equal(audio.state().phase,'error');
  assert.equal(audio.play('日本語','test'),true);
});
test('long playback is chunked and stops without speaking the remaining chunks',()=>{
  const m=speechMock();m.h.ctx.longText='こんにちは。'.repeat(70);m.h.run("japaneseAudio.play(longText,'long')");
  assert.ok(m.spoken[0].text.length<=160);m.spoken[0].onstart();m.spoken[0].onend();assert.equal(m.spoken.length,2);
  m.h.run('japaneseAudio.stop()');assert.equal(m.spoken[1].onend,null);
});
test('navigation, hidden tabs and learner changes safely cancel speech',()=>{
  const m=speechMock();
  for(const type of ['hashchange','pagehide']){m.h.run("japaneseAudio.play('こんにちは','one')");for(const fn of m.h.windowEvents[type]){if(type==='hashchange' && fn.name==='renderRoute')continue;fn();}assert.equal(m.h.run('japaneseAudio.state().owner'),null);}
  m.h.run("japaneseAudio.play('こんにちは','one')");m.h.ctx.document.hidden=true;for(const fn of m.h.documentEvents.visibilitychange)fn();assert.equal(m.h.run('japaneseAudio.state().owner'),null);
  m.h.run("japaneseAudio.play('こんにちは','one');document.dispatchEvent(new Event('learner-changed'))");assert.equal(m.h.run('japaneseAudio.state().owner'),null);
});
test('only displayed Japanese reply fields are playable; private metadata and English stay out',()=>{
  const m=speechMock();m.h.ctx.reply={message:'Say: こんにちは！ Hello.',examples:['水をください。'],correction:{original:'水ください',improved:'水をください。'},explanation:'Internal discussion',private_rag:'秘密の文章',exercise:{question:'Choose one',choices:[],hint:'秘密の答え'}};
  m.h.run('renderReply(reply)');const article=m.h.elements.get('conversation').children.at(-1);
  const players=article.children.filter(e=>e.className==='audio-player');assert.equal(players.length,3);
  for(const player of players)player.children[0].children[0].listeners.click();
  assert.equal(m.spoken.map(u=>u.text).join('|'),'こんにちは！|水をください。|水をください。');assert.equal(m.h.requests.length,0);
  assert.equal(m.h.run("japanesePlaybackText('Only English instructions.')"),'');
});
test('audio controls reflect loading, playing, errors and detached-player cleanup',()=>{
  const m=speechMock();m.h.run("addMessage('tutor','こんにちは。')");const article=m.h.elements.get('conversation').children.at(-1), player=article.children.at(-1);
  const [actions,,,status]=player.children;actions.children[0].listeners.click();assert.match(status.textContent,/Preparing/);m.spoken.at(-1).onstart();assert.match(status.textContent,/Playing/);
  actions.children[1].listeners.click();assert.match(status.textContent,/stopped/);player.isConnected=false;
  assert.doesNotThrow(()=>m.h.run('japaneseAudio.setRate(.75)'));
});
test('listening bank validates every answer and rejects invalid choices',()=>{
  const h=harness(),bank=h.run('listeningExercises');assert.equal(bank.length,8);assert.equal(new Set(bank.map(e=>e.id)).size,8);
  for(const e of bank){h.ctx.exercise=e;assert.match(e.text,/[ぁ-んァ-ヶ一-龯]/);for(let i=0;i<e.choices.length;i++){h.ctx.choice=i;assert.equal(h.run('listeningCheck(exercise,choice)'),i===e.answer);}h.ctx.choice=-1;assert.throws(()=>h.run('listeningCheck(exercise,choice)'),/Choose/);}
});
function startListening(h,level='N5'){h.elements.get('listening-level').value=level;h.elements.get('listening-start').listeners.click();}
function answerListening(h,choice){h.elements.get('listening-choices').selected={value:String(choice)};h.elements.get('listening-answer-form').listeners.submit({preventDefault(){}});}
test('listening requires playback or assisted reveal, hides transcript until answer, and scores once',()=>{
  const m=speechMock(),h=m.h;startListening(h);assert.equal(h.elements.get('listening-transcript').hidden,true);assert.equal(m.spoken.length,0);
  answerListening(h,1);assert.match(h.elements.get('listening-error').textContent,/Play/);assert.equal(h.run('listeningState.results.length'),0);
  const player=h.elements.get('listening-audio').children[0];player.children[0].children[0].listeners.click();m.spoken.at(-1).onstart();answerListening(h,1);answerListening(h,1);
  assert.equal(h.run('listeningState.results.length'),1);assert.equal(h.run('listeningState.results[0].correct'),true);assert.equal(h.run('listeningState.results[0].assisted'),false);
  assert.equal(h.elements.get('listening-transcript').hidden,false);assert.match(h.elements.get('listening-feedback').textContent,/Correct/);assert.equal(h.requests.length,0);
});
test('assisted listening remains available without voices and summaries separate assisted attempts',()=>{
  const h=harness();startListening(h,'N4');
  for(let i=0;i<4;i++){h.elements.get('listening-reveal').listeners.click();assert.equal(h.elements.get('listening-transcript').hidden,false);assert.equal(h.run('listeningState.assisted'),true);answerListening(h,h.run('listeningState.exercises[listeningState.index].answer'));h.elements.get('listening-next').listeners.click();}
  assert.match(h.elements.get('listening-summary-text').textContent,/without transcript: 0 correct of 0.*Assisted practice: 4 correct of 4/);
  assert.equal(h.run('listeningState'),null);assert.equal(h.elements.get('listening-summary').hidden,false);assert.equal(h.requests.length,0);
});
test('listening navigation retains answer and attempt without API calls or hidden transcripts appearing',async()=>{
  const h=harness();h.run('appReady=true');startListening(h);h.elements.get('listening-choices').selected={value:'1'};
  h.ctx.location.hash='#placement';await h.run('renderRoute()');h.ctx.location.hash='#study/listening';await h.run('renderRoute()');
  assert.equal(h.elements.get('listening-choices').selected.value,'1');assert.equal(h.elements.get('listening-transcript').hidden,true);
  assert.equal(h.elements.get('jlpt-panel').hidden,true);assert.equal(h.elements.get('personalized-study').hidden,true);assert.equal(h.elements.get('listening-panel').hidden,false);assert.equal(h.requests.length,0);
});

function recordingMock(config={}) {
  const tracks=[],recorders=[],revoked=[],created=[],requests=[],timers=new Map();let time=0,sequence=0;
  function stream(){const listeners=new Map();const track={readyState:'live',stops:0,stop(){this.stops++;this.readyState='ended';},addEventListener(n,fn){listeners.set(n,fn);},removeEventListener(n){listeners.delete(n);},end(){this.readyState='ended';listeners.get('ended')?.();}};tracks.push(track);return {getTracks:()=>[track],getAudioTracks:()=>[track]};}
  class Recorder {
    static isTypeSupported(type){return (config.formats || ['audio/webm;codecs=opus']).includes(type);}
    constructor(source,options){if(config.initError && (!config.optionsOnly || options))throw {name:config.initError};this.stream=source;this.options=options;this.mimeType=options?.mimeType || config.defaultMime || 'audio/webm';this.state='inactive';recorders.push(this);}
    start(slice){if(config.startError)throw Error('start');this.slice=slice;this.state='recording';}
    stop(){this.state='inactive';this.stops=(this.stops||0)+1;if(config.stopError)throw Error('stop');}
    data(size=5,type=this.mimeType){this.ondataavailable?.({data:new Blob(['a'.repeat(size)],{type})});}
    finish(size=5){this.data(size);this.onstop?.();}
  }
  const mediaDevices={getUserMedia(options){requests.push(options);return config.permission ? config.permission(stream) : config.denied ? Promise.reject({name:config.denied}) : Promise.resolve(stream());}};
  const urls={createObjectURL(blob){created.push(blob);if(config.urlError)throw Error('url');return `blob:local-${created.length}`;},revokeObjectURL(url){revoked.push(url);}};
  const schedule=(fn,ms,interval=false)=>{const id=++sequence;timers.set(id,{fn,due:time+ms,ms,interval});return id;};
  const deps={secure:config.secure!==false,mediaDevices,Recorder,BlobType:Blob,urls,now:()=>time,schedule:(fn,ms)=>schedule(fn,ms),unschedule:id=>timers.delete(id),repeat:(fn,ms)=>schedule(fn,ms,true),unrepeat:id=>timers.delete(id),maxBytes:config.maxBytes || 8*1024*1024,beforeStart:config.beforeStart || (()=>{})};
  const h=harness({isSecureContext:true,mediaDevices,MediaRecorder:Recorder,Blob,URL:urls,now:()=>time});h.ctx.recorderDeps=deps;
  const recorder=h.run('createBrowserRecorder(recorderDeps)');
  function advance(ms){const target=time+ms;while(true){const entry=[...timers].filter(([,t])=>t.due<=target).sort((a,b)=>a[1].due-b[1].due)[0];if(!entry)break;const [id,t]=entry;time=t.due;if(t.interval)t.due+=t.ms;else timers.delete(id);t.fn();}time=target;}
  return {h,recorder,deps,tracks,recorders,revoked,created,requests,timers,stream,advance};
}
test('recorder detects support and secure context without requesting a microphone at load',()=>{
  const m=recordingMock();assert.equal(m.recorder.state().availability,'supported');assert.equal(m.requests.length,0);
  m.h.ctx.noSupport={secure:true};assert.equal(m.h.run('createBrowserRecorder(noSupport).state().availability'),'unsupported');
  assert.equal(recordingMock({secure:false}).recorder.state().availability,'insecure');
});
test('granted recording follows start, stop, processing and local preview with actual MIME',async()=>{
  const m=recordingMock();await m.recorder.start();assert.equal(m.recorder.state().phase,'recording');assert.deepEqual(JSON.parse(JSON.stringify(m.requests[0])),{audio:true,video:false});assert.equal(m.recorders[0].slice,250);
  m.advance(1500);assert.equal(m.recorder.state().elapsedMs,1500);m.recorder.stop();assert.equal(m.recorder.state().phase,'processing');assert.equal(m.tracks[0].stops,1);
  m.recorders[0].finish();assert.equal(m.recorder.state().phase,'preview');assert.equal(m.recorder.recording().mimeType,'audio/webm;codecs=opus');assert.equal(m.recorder.recording().blob.size,5);assert.equal(m.timers.size,0);
});
test('microphone permission and device errors give useful messages and allow explicit retry',async()=>{
  for(const [name,pattern] of [['NotAllowedError',/denied/],['NotFoundError',/No microphone/],['NotReadableError',/in use/],['SecurityError',/blocked/],['AbortError',/interrupted/]]){
    const m=recordingMock({denied:name});await m.recorder.start();assert.equal(m.recorder.state().phase,'error');assert.match(m.recorder.state().message,pattern);assert.equal(m.recorder.state().permissionPending,false);assert.equal(m.timers.size,0);assert.equal(m.requests.length,1);
    await m.recorder.start();assert.equal(m.requests.length,2);
  }
});
test('cancel releases tracks/timers and stale recording events cannot create a preview',async()=>{
  const m=recordingMock();await m.recorder.start();const lateData=m.recorders[0].ondataavailable,lateStop=m.recorders[0].onstop;
  m.recorder.cancel();lateData({data:new Blob(['late'])});lateStop();assert.equal(m.tracks[0].stops,1);assert.equal(m.timers.size,0);assert.equal(m.recorder.state().phase,'idle');assert.equal(m.created.length,0);
});
test('cancelled permission requests release late streams and never request twice concurrently',async()=>{
  let grant;const m=recordingMock({permission:stream=>new Promise(resolve=>{grant=()=>resolve(stream());})});
  const pending=m.recorder.start();assert.equal(m.recorder.state().phase,'requesting');await m.recorder.start();assert.equal(m.requests.length,1);
  m.recorder.cancel();await m.recorder.start();assert.equal(m.requests.length,1);assert.equal(m.recorder.state().permissionPending,true);
  grant();await pending;assert.equal(m.tracks[0].stops,1);assert.equal(m.recorders.length,0);assert.equal(m.recorder.state().permissionPending,false);
});
test('record again and discard revoke old object URLs and keep no stored clip',async()=>{
  const m=recordingMock();await m.recorder.start();m.recorder.stop();m.recorders[0].finish();assert.equal(m.recorder.state().url,'blob:local-1');
  await m.recorder.start();assert.deepEqual(m.revoked,['blob:local-1']);assert.equal(m.recorder.recording(),null);
  m.recorder.stop();m.recorders[1].finish();m.recorder.cancel();assert.deepEqual(m.revoked,['blob:local-1','blob:local-2']);assert.equal(m.recorder.recording(),null);
});
test('duration deadline automatically stops at sixty seconds and releases the microphone',async()=>{
  const m=recordingMock();await m.recorder.start();m.advance(60000);assert.equal(m.recorder.state().phase,'processing');assert.equal(m.tracks[0].stops,1);assert.equal(m.recorder.state().elapsedMs,60000);
  m.recorders[0].finish();assert.match(m.recorder.state().message,/60-second limit/);assert.equal(m.timers.size,0);
});
test('size guard discards oversized buffers including the final chunk',async()=>{
  const m=recordingMock({maxBytes:8});await m.recorder.start();m.recorders[0].data(5);m.recorder.stop();m.recorders[0].data(4);
  assert.equal(m.recorder.state().phase,'error');assert.match(m.recorder.state().message,/size limit/);assert.equal(m.recorder.recording(),null);assert.equal(m.created.length,0);assert.equal(m.recorder.state().bytes,0);assert.equal(m.tracks[0].stops,1);
});
test('empty recordings and object URL failures recover with no active resources',async()=>{
  for(const config of [{},{urlError:true}]){const m=recordingMock(config);await m.recorder.start();m.recorder.stop();m.recorders[0].finish(config.urlError?5:0);assert.equal(m.recorder.state().phase,'error');assert.equal(m.recorder.recording(),null);assert.equal(m.recorder.state().url,'');assert.equal(m.timers.size,0);assert.equal(m.tracks[0].stops,1);}
});
test('recorder initialization, start, stop and interrupted-stream failures release capture',async()=>{
  for(const config of [{initError:'NotReadableError'},{startError:true},{stopError:true},{}]){
    const m=recordingMock(config);await m.recorder.start();if(config.stopError)m.recorder.stop();else if(!config.initError&&!config.startError)m.tracks[0].end();
    assert.equal(m.recorder.state().phase,'error');assert.equal(m.tracks[0].stops,1);assert.equal(m.recorder.recording(),null);assert.equal(m.timers.size,0);
  }
});
test('recording error and missing finalization event do not leave an active recorder',async()=>{
  const m=recordingMock();await m.recorder.start();m.recorders[0].onerror({error:Error('failure')});assert.equal(m.recorder.state().phase,'error');assert.equal(m.tracks[0].stops,1);
  await m.recorder.start();m.recorder.stop();m.advance(5000);assert.equal(m.recorder.state().phase,'error');assert.match(m.recorder.state().message,/could not finish/);assert.equal(m.timers.size,0);
});
test('MIME negotiation checks WebM/MP4 and uses the native default when necessary',async()=>{
  for(const [config,expected] of [[{formats:['audio/mp4']},'audio/mp4'],[{formats:[],defaultMime:'audio/ogg'},'audio/ogg']]){
    const m=recordingMock(config);await m.recorder.start();assert.equal(m.recorders[0].options?.mimeType,config.formats[0]);m.recorder.stop();m.recorders[0].finish();assert.equal(m.recorder.recording().blob.type,expected);
  }
});
test('an advertised but failing MIME option falls back to the browser default',async()=>{
  const m=recordingMock({initError:'NotSupportedError',optionsOnly:true,defaultMime:'audio/mp4'});await m.recorder.start();assert.equal(m.recorder.state().phase,'recording');assert.equal(m.recorders[0].options,undefined);m.recorder.stop();m.recorders[0].finish();assert.equal(m.recorder.recording().mimeType,'audio/mp4');
});
test('navigation, panel close, hidden tabs and learner changes cancel UI recording',async()=>{
  for(const trigger of ['hashchange','pagehide','visibilitychange','learner-changed','toggle']){
    const m=recordingMock(),h=m.h;await h.run('browserRecorder.start()');
    if(trigger==='hashchange'||trigger==='pagehide'){for(const fn of h.windowEvents[trigger])if(fn.name!=='renderRoute')fn();}
    else if(trigger==='visibilitychange'){h.ctx.document.hidden=true;for(const fn of h.documentEvents[trigger])fn();}
    else if(trigger==='toggle'){h.elements.get('recording-card').open=false;h.elements.get('recording-card').listeners.toggle();}
    else h.run("document.dispatchEvent(new Event('learner-changed'))");
    assert.equal(h.run('browserRecorder.state().phase'),'idle');assert.equal(m.tracks[0].stops,1);assert.equal(h.requests.length,0);
  }
});
test('recorder UI supports preview/retry/discard without sending chat or storing audio',async()=>{
  const m=recordingMock(),h=m.h;await h.elements.get('recording-start').listeners.click();assert.equal(h.elements.get('recording-stop').hidden,false);
  h.elements.get('recording-stop').listeners.click();m.recorders[0].finish();assert.equal(h.elements.get('recording-play').hidden,false);assert.equal(h.elements.get('recording-start').textContent,'Record again');
  await h.elements.get('recording-play').listeners.click();assert.equal(h.elements.get('recording-preview').paused,false);
  h.elements.get('recording-discard').listeners.click();assert.equal(h.elements.get('recording-preview').src,'');assert.equal(h.elements.get('recording-preview').paused,true);assert.deepEqual(m.revoked,['blob:local-1']);assert.equal(h.requests.length,0);assert.equal(h.storage.size,0);
});
test('TTS stops before microphone use and cannot start during permission/recording',async()=>{
  const m=recordingMock(),speech=speechMock();
  m.h.ctx.speechDeps={synth:speech.synth,Utterance:speech.Utterance};m.h.run('japaneseAudio.destroy()');
  // Exercise the production UI listeners with both native API stubs in one harness.
  const h=harness({isSecureContext:true,mediaDevices:m.deps.mediaDevices,MediaRecorder:m.deps.Recorder,Blob,URL:m.deps.urls,speechSynthesis:speech.synth,SpeechSynthesisUtterance:speech.Utterance});
  h.run("japaneseAudio.play('こんにちは','tutor')");assert.equal(speech.spoken.length,1);await h.run('browserRecorder.start()');assert.equal(h.run('japaneseAudio.state().owner'),null);assert.equal(h.run('japaneseAudio.state().blocked'),true);
  assert.equal(h.run("japaneseAudio.play('こんにちは','tutor')"),false);assert.equal(speech.spoken.length,1);
  h.run('browserRecorder.stop()');m.recorders[0].finish();assert.equal(h.run('japaneseAudio.state().blocked'),false);
  await h.elements.get('recording-play').listeners.click();h.run("japaneseAudio.play('こんにちは','tutor')");assert.equal(h.elements.get('recording-preview').paused,true);assert.equal(h.requests.length,0);
});
test('cancelled permission requests restore TTS while late microphone grants are released',async()=>{
  let grant;const m=recordingMock({permission:stream=>new Promise(resolve=>{grant=()=>resolve(stream());})}),speech=speechMock();
  const h=harness({isSecureContext:true,mediaDevices:m.deps.mediaDevices,MediaRecorder:m.deps.Recorder,Blob,URL:m.deps.urls,speechSynthesis:speech.synth,SpeechSynthesisUtterance:speech.Utterance});
  const pending=h.run('browserRecorder.start()');assert.equal(h.run('japaneseAudio.state().blocked'),true);h.run('browserRecorder.cancel()');assert.equal(h.run('japaneseAudio.state().blocked'),false);
  h.run("japaneseAudio.play('こんにちは','tutor')");grant();await pending;assert.equal(m.tracks[0].stops,1);assert.equal(m.recorders.length,0);assert.equal(speech.spoken.length,1);
});
test('preview playback failures are helpful and stale promises cannot resurrect a discarded preview',async()=>{
  const m=recordingMock(),h=m.h;await h.run('browserRecorder.start()');h.run('browserRecorder.stop()');m.recorders[0].finish();
  h.elements.get('recording-preview').play=()=>Promise.reject(Error('codec'));await h.elements.get('recording-play').listeners.click();assert.equal(h.elements.get('recording-preview-error').hidden,false);
  let reject;h.elements.get('recording-preview').play=()=>new Promise((_,fail)=>{reject=fail;});const pending=h.elements.get('recording-play').listeners.click();h.run('browserRecorder.cancel()');reject(Error('discarded'));await pending;
  assert.equal(h.elements.get('recording-preview-error').hidden,true);assert.equal(h.elements.get('recording-preview').hidden,true);assert.equal(h.requests.length,0);
});
