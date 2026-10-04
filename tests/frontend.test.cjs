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
    append(...children) { for(const child of children){if(child.parentElement)child.parentElement.children=child.parentElement.children.filter(c=>c!==child);child.parentElement=this;this.children.push(child);} }
    replaceChildren(...children) { this.children=children; this.textContent=''; }
    cloneNode() { return new Element(this.tagName); }
    get firstElementChild() { return this.children[0] || new Element(); }
    get childElementCount() { return this.children.length; }
    setAttribute(k,v) { this.attributes[k]=v; }
    removeAttribute(k) { delete this.attributes[k]; if(k==='src')this.src=''; }
    pause() { this.paused=true; }
    play() { this.paused=false; return Promise.resolve(); }
    load() { this.loaded=true; }
    addEventListener(type, fn) { const previous=this.listeners[type];this.listeners[type]=previous ? (...args)=>{previous(...args);return fn(...args);} : fn; }
    dispatchEvent(event) { return this.listeners[event.type]?.(event); }
    querySelectorAll() { return []; }
    querySelector() { return this.selected || null; }
    closest() { return null; }
    focus() { this.focused=true; }
  }
  for (const m of html.matchAll(/<([\w-]+)\b[^>]*\bid="([^"]+)"[^>]*>/g)) { const e=new Element(m[1]); e.hidden=/\bhidden\b/.test(m[0]); elements.set(m[2],e); }
  elements.get('review-minutes').value='10'; elements.get('onboarding-goal-select').value='general';
  const windowEvents = {}, documentEvents = {};
  const ctx = vm.createContext({console, Event, AbortController, Blob, URLSearchParams, Intl, TypeError, SyntaxError, setInterval:()=>1, clearInterval(){}, setTimeout:()=>1, clearTimeout(){}, crypto:require('node:crypto').webcrypto,
    document:{getElementById:id=>elements.get(id),createElement:tag=>new Element(tag),querySelectorAll:()=>[],querySelector:selector=>selector==='.skip-link'?new Element('a'):null,addEventListener(type,fn){(documentEvents[type] ||= []).push(fn);},dispatchEvent(event){for(const fn of documentEvents[event.type] || []) fn(event);}},
    window:{...audio,addEventListener(type,fn){(windowEvents[type] ||= []).push(fn);},location:{assign(url){ctx.redirect=url;}}},location:{hash:''},navigator:{onLine:true,mediaDevices:audio.mediaDevices},performance:{now:audio.now || (()=>0)},
    localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    sessionStorage:{getItem:()=>null,setItem(){}},
    fetch:async (url, options={})=>{ requests.push({url,...options}); throw new TypeError('offline'); }
  });
  // Run all real scripts; bootstrap is invoked explicitly by each test.
  for (const name of scripts) { let source=fs.readFileSync(path.join(root,name),'utf8'); if(name==='shell.js') source=source.replace(/boot\(\);\s*$/, ''); vm.runInContext(source,ctx,{filename:name}); if(name==='flashcard-catalog.js') vm.runInContext('flashcardCatalog = validateFlashcardCatalog('+fs.readFileSync(path.join(root,'flashcard-catalog.json'),'utf8')+')',ctx); }
  return {ctx,elements,requests,storage,windowEvents,documentEvents,run:source=>vm.runInContext(source,ctx)};
}

function flashcardStart(h, category='vocabulary', direction='ja-en') {
  h.elements.get('flashcard-deck').value=category; h.elements.get('flashcard-direction').value=direction;
  h.elements.get('flashcard-setup').listeners.submit({preventDefault(){}});
}

function dueHarness(items=2) {
  const h=harness();h.run("placementLearnerId='learner';flashcardMode='due'");h.ctx.location.hash='#study/flashcards';
  const cards=Array.from({length:items},(_,i)=>({review_id:'review-'+i,version:1,dimension:'reading',card:{front:'Read 学校 in kana.',back:'がっこう',category:'vocabulary',audio_text:'学校'}}));
  h.ctx.fetch=async (url,options={})=>{
    h.requests.push({url,...options});
    if(url.endsWith('/history'))return {ok:true,json:async()=>({items:[]})};
    if(url.endsWith('/flashcards'))return {ok:true,json:async()=>({items:cards,due_count:items,unsupported_count:0})};
    const body=JSON.parse(options.body);return {ok:true,json:async()=>({completed:true,review_id:url.split('/').at(-2),submission_id:body.submission_id})};
  };
  return h;
}
test('due queue shows the front only, reveal enables ratings without saving',async()=>{
  const h=dueHarness();await h.run('loadDueFlashcards()');
  assert.equal(h.elements.get('flashcard-front').textContent,'Read 学校 in kana.');
  assert.equal(h.elements.get('flashcard-answer').hidden,true);assert.equal(h.elements.get('flashcard-ratings').hidden,true);
  await h.run("saveFlashcardRating('good')");assert.equal(h.requests.filter(r=>r.method==='POST').length,0);
  h.elements.get('flashcard-reveal').listeners.click();
  assert.match(descendantText(h.elements.get('flashcard-answer')),/がっこう/);assert.equal(h.elements.get('flashcard-ratings').hidden,false);
  assert.equal(h.elements.get('flashcard-rate-good').disabled,false);assert.equal(h.run('dueFlashcards.completed.size'),0);
});
test('due save blocks double taps and advances only after a confirmed receipt',async()=>{
  const h=dueHarness();await h.run('loadDueFlashcards()');h.elements.get('flashcard-reveal').listeners.click();
  const fetch=h.ctx.fetch;let resolve;h.ctx.fetch=(url,opts)=>opts?.method==='POST'?new Promise(r=>resolve=()=>r(fetch(url,opts))):fetch(url,opts);
  const saving=h.run("saveFlashcardRating('good')");await h.run("saveFlashcardRating('easy')");
  assert.equal(h.run('dueFlashcards.index'),0);assert.equal(h.elements.get('flashcard-rate-good').disabled,true);
  assert.equal(h.run('dueFlashcards.completed.size'),0);resolve();await saving;
  assert.equal(h.requests.filter(r=>r.method==='POST').length,1);assert.equal(h.run('dueFlashcards.index'),1);
  assert.equal(h.run('dueFlashcards.completed.size'),1);assert.equal(h.elements.get('flashcard-answer').hidden,true);
});
test('ambiguous save retry keeps UUID and original rating and cannot falsely complete',async()=>{
  const h=dueHarness(1);await h.run('loadDueFlashcards()');h.elements.get('flashcard-reveal').listeners.click();
  const fetch=h.ctx.fetch;let failedBody;h.ctx.fetch=async(url,opts)=>{if(opts?.method==='POST'){failedBody=opts.body;throw new TypeError('offline');}return fetch(url,opts);};
  await h.run("saveFlashcardRating('hard')");assert.equal(h.run('dueFlashcards.completed.size'),0);assert.equal(h.run('dueFlashcards.index'),0);
  assert.equal(h.elements.get('flashcard-due-retry').hidden,false);assert.equal(h.elements.get('flashcard-due-load').disabled,true);
  h.ctx.fetch=fetch;await h.elements.get('flashcard-due-retry').listeners.click();
  assert.equal(h.requests.find(r=>r.method==='POST').body,failedBody);assert.match(h.elements.get('flashcard-due-status').textContent,/Batch complete! 1 completed/);
  assert.equal(h.elements.get('flashcard-session').hidden,true);
});
test('changed due review requires reload and cannot be counted',async()=>{
  const h=dueHarness();await h.run('loadDueFlashcards()');h.elements.get('flashcard-reveal').listeners.click();
  h.ctx.fetch=async()=>({ok:false,json:async()=>({error:{code:'review_changed',message:'Review changed.'}})});
  await h.run("saveFlashcardRating('good')");assert.equal(h.run('dueFlashcards.completed.size'),0);
  assert.equal(h.elements.get('flashcard-due-retry').hidden,true);assert.equal(h.elements.get('flashcard-due-load').disabled,false);
});
test('an older history response cannot hide a newly confirmed review',async()=>{
  const h=dueHarness(1), fetch=h.ctx.fetch;let resolve, calls=0;
  const entry=title=>({title,dimension:'reading',rating:'good',method:'self_report',reviewed_at:'2026-10-04T00:00:00Z'});
  h.ctx.fetch=(url,opts)=>{
    if(url.endsWith('/history')) {
      if(++calls===1)return new Promise(r=>resolve=()=>r({ok:true,json:async()=>({items:[entry('Old history')]})}));
      return Promise.resolve({ok:true,json:async()=>({items:[entry('Saved review')]})});
    }
    return fetch(url,opts);
  };
  await h.run('loadDueFlashcards()');h.elements.get('flashcard-reveal').listeners.click();await h.run("saveFlashcardRating('good')");
  await new Promise(setImmediate);resolve();await new Promise(setImmediate);
  assert.match(descendantText(h.elements.get('flashcard-due-history')),/Saved review/);
  assert.doesNotMatch(descendantText(h.elements.get('flashcard-due-history')),/Old history/);
});
test('stale queue and save responses never populate a changed learner',async()=>{
  const h=dueHarness();let resolve;const fetch=h.ctx.fetch;
  h.ctx.fetch=(url,opts)=>url.endsWith('/flashcards')?new Promise(r=>resolve=()=>r(fetch(url,opts))):fetch(url,opts);
  const loading=h.run('loadDueFlashcards()');h.run("placementLearnerId=null;document.dispatchEvent(new Event('learner-changed'))");resolve();await loading;
  assert.equal(h.run('dueFlashcards.items.length'),0);
  h.run("placementLearnerId='learner'");h.ctx.fetch=fetch;await h.run('loadDueFlashcards()');h.elements.get('flashcard-reveal').listeners.click();
  h.ctx.fetch=(url,opts)=>opts?.method==='POST'?new Promise(r=>resolve=()=>r(fetch(url,opts))):fetch(url,opts);
  const saving=h.run("saveFlashcardRating('good')");h.run("placementLearnerId=null;document.dispatchEvent(new Event('learner-changed'))");resolve();await saving;
  assert.equal(h.run('dueFlashcards.completed.size'),0);assert.equal(h.elements.get('flashcard-mode-free').disabled,false);
});
test('mode switching preserves free practice position and does not post ratings',async()=>{
  const h=dueHarness();h.run("flashcardMode='free'");flashcardStart(h);h.elements.get('flashcard-next').listeners.click();
  h.run("setFlashcardMode('due')");await new Promise(setImmediate);h.run("setFlashcardMode('free')");
  assert.equal(h.run('flashcards.snapshot().index'),1);assert.equal(h.elements.get('flashcard-controls').hidden,false);
  assert.equal(h.elements.get('flashcard-free-options').hidden,false);assert.equal(h.elements.get('flashcard-ratings').hidden,true);
  assert.equal(h.requests.filter(r=>r.method==='POST').length,0);
});
test('due empty, no profile and network failure are distinct recoverable states',async()=>{
  const h=dueHarness(0);await h.run('loadDueFlashcards()');assert.match(h.elements.get('flashcard-due-status').textContent,/caught up/);
  h.run('placementLearnerId=null');await h.run('loadDueFlashcards()');assert.equal(h.elements.get('flashcard-due-profile').hidden,false);
  h.run("placementLearnerId='learner'");h.ctx.fetch=async()=>{throw new TypeError('offline');};await h.run('loadDueFlashcards()');
  assert.equal(h.elements.get('flashcard-due-error').hidden,false);assert.equal(h.elements.get('flashcard-due-load').disabled,false);
  assert.doesNotMatch(h.elements.get('flashcard-due-status').textContent,/caught up/);
});
test('due reveal TTS reads the Japanese target without activity or review writes',async()=>{
  const m=speechMock(),h=m.h;h.run("placementLearnerId='learner';flashcardMode='due';dueFlashcards={...freshDueFlashcards(),learner:'learner',loaded:true,total:1,items:[{review_id:'r',dimension:'production',card:{category:'vocabulary',front:'Recall water in Japanese.',back:'水',audio_text:'水'}}]}");h.ctx.location.hash='#study/flashcards';
  h.elements.get('flashcard-reveal').listeners.click();const player=h.elements.get('flashcard-answer').children.at(-1);player.children[0].children[0].listeners.click();
  assert.equal(m.spoken.at(-1).text,'水');assert.equal(h.requests.length,0);assert.equal(h.run('dueFlashcards.completed.size'),0);
});
test('practice catalog is cached, retries failed loads and retains validated content',async()=>{
  const h=harness();h.run('flashcardCatalog=null');const catalog=JSON.parse(fs.readFileSync(path.join(root,'flashcard-catalog.json'),'utf8'));let calls=0;
  h.ctx.fetch=async()=>{calls++;throw new TypeError('offline');};await h.run('loadFlashcards()');
  assert.equal(h.elements.get('flashcard-start').disabled,true);assert.equal(h.elements.get('flashcard-catalog-retry').hidden,false);
  h.ctx.fetch=async()=>{calls++;return {ok:true,json:async()=>catalog};};await h.run('loadFlashcards()');await h.run('loadFlashcards()');
  assert.equal(calls,2);assert.equal(h.run('flashcardCatalog.length'),30);assert.equal(h.elements.get('flashcard-start').disabled,false);
});
function descendantText(element) { return [element.textContent,...element.children.map(descendantText)].join(' '); }
test('flashcard catalog validates, has stable unique IDs and appropriate decks',()=>{
  const h=harness(), catalog=h.run('flashcardCatalog');
  assert.equal(catalog.length,30);assert.equal(new Set(catalog.map(c=>c.id)).size,30);
  for(const [category,count] of [['vocabulary',12],['kanji',10],['grammar',8]]) assert.equal(catalog.filter(c=>c.category===category).length,count);
  assert.equal(catalog[0].id,'fc_vocab_neko');assert.equal(catalog[16].topic_id,'kanji_gaku');assert.equal(catalog[22].topic_id,'tai_form');
  assert.ok(catalog.every(c=>c.example_japanese&&c.example_translation));assert.ok(Object.isFrozen(catalog));
});
test('flashcard malformed records and duplicate identities are rejected',()=>{
  const h=harness();
  for(const mutation of ["id:''","category:'unknown'","front:''","meaning:''","reading:null","example_translation:null","tags:'bad'","topic_id:'invalid id'"]) {
    assert.throws(()=>h.run(`validateFlashcardCatalog([{...flashcardCatalog[0],${mutation}}])`),/Invalid|Missing|needs/);
  }
  assert.throws(()=>h.run('validateFlashcardCatalog([flashcardCatalog[0],flashcardCatalog[0]])'),/duplicate/);
  assert.throws(()=>h.run('validateFlashcardCatalog(null)'),/array/);
});
test('vocabulary Japanese question excludes answer until explicit reveal',()=>{
  const h=harness();flashcardStart(h);
  assert.equal(h.elements.get('flashcard-front').textContent,'猫');assert.equal(h.elements.get('flashcard-front').attributes.lang,'ja');
  assert.equal(h.elements.get('flashcard-answer').hidden,true);assert.equal(descendantText(h.elements.get('flashcard-answer')),'');
  h.elements.get('flashcard-reveal').listeners.click();assert.equal(h.elements.get('flashcard-answer').hidden,false);
  assert.match(descendantText(h.elements.get('flashcard-answer')),/cat.*ねこ.*猫がいます/);
  assert.equal(h.elements.get('flashcard-answer').focused,true);assert.equal(h.elements.get('flashcard-reveal').hidden,true);
});
test('reverse vocabulary asks English then reveals Japanese and kana',()=>{
  const h=harness();flashcardStart(h,'vocabulary','en-ja');
  assert.equal(h.elements.get('flashcard-front').textContent,'cat');assert.equal(h.elements.get('flashcard-front').attributes.lang,'en');
  assert.equal(h.elements.get('flashcard-answer').children.length,0);
  h.elements.get('flashcard-reveal').listeners.click();assert.match(descendantText(h.elements.get('flashcard-answer')),/猫.*ねこ/);
  h.elements.get('flashcard-next').listeners.click();assert.equal(h.run('flashcards.snapshot().direction'),'en-ja');assert.equal(h.elements.get('flashcard-front').textContent,'school');
});
for(const category of ['kanji','grammar']) test(`${category} uses specialized Japanese presentation instead of reverse`,()=>{
  const h=harness();flashcardStart(h,category,'en-ja');assert.equal(h.run('flashcards.snapshot().direction'),'ja-en');
  h.elements.get('flashcard-reveal').listeners.click();assert.match(descendantText(h.elements.get('flashcard-answer')),category==='kanji'?/one.*ひと.*一つ/:/want to do.*verb stem.*日本に行きたいです/);
  h.elements.get('flashcard-deck').listeners.change();assert.equal(h.elements.get('flashcard-direction').disabled,true);
});
test('next and previous clamp boundaries and remove revealed content',()=>{
  const h=harness();flashcardStart(h);assert.equal(h.elements.get('flashcard-prev').disabled,true);
  h.elements.get('flashcard-reveal').listeners.click();h.elements.get('flashcard-next').listeners.click();assert.equal(h.run('flashcards.snapshot().index'),1);
  assert.equal(h.elements.get('flashcard-answer').children.length,0);assert.equal(h.elements.get('flashcard-answer').hidden,true);
  h.elements.get('flashcard-prev').listeners.click();h.elements.get('flashcard-prev').listeners.click();assert.equal(h.run('flashcards.snapshot().index'),0);
});
test('shuffle has no duplicates, preserves direction and resets position/reveal',()=>{
  const h=harness();h.run("const shuffled=createFlashcardSession(flashcardCatalog,()=>0); shuffled.start('vocabulary','en-ja'); shuffled.reveal(); shuffled.move(3); shuffled.restart(true)");
  const state=h.run('shuffled.snapshot()');assert.equal(state.cards.length,12);assert.equal(new Set(state.cards.map(c=>c.id)).size,12);assert.notEqual(state.cards[0].id,'fc_vocab_neko');
  assert.equal(state.index,0);assert.equal(state.revealed,false);assert.equal(state.direction,'en-ja');
});
test('final card finishes session and restart is transient',()=>{
  const h=harness();flashcardStart(h);for(let i=0;i<11;i++)h.elements.get('flashcard-next').listeners.click();
  assert.equal(h.elements.get('flashcard-next').textContent,'Finish session');h.elements.get('flashcard-next').listeners.click();
  assert.equal(h.elements.get('flashcard-completion').hidden,false);assert.equal(h.elements.get('flashcard-stage').hidden,true);
  assert.match(h.elements.get('flashcard-completion-text').textContent,/no reviews or progress were saved/);
  h.elements.get('flashcard-again').listeners.click();assert.equal(h.run('flashcards.snapshot().finished'),false);assert.equal(h.run('flashcards.snapshot().index'),0);
  assert.equal(h.elements.get('flashcard-progress').textContent,'1 / 12 cards · vocabulary · Beginner');
});
test('empty flashcard deck shows recovery and does not retain an answer',()=>{
  const h=harness();flashcardStart(h);h.run("flashcards.start('missing'); renderFlashcard()");
  assert.equal(h.elements.get('flashcard-empty').hidden,false);assert.equal(h.elements.get('flashcard-session').hidden,true);assert.equal(h.elements.get('flashcard-answer').children.length,0);
});
test('flashcard TTS uses Japanese public text and cleans up on navigation',()=>{
  const m=speechMock(),h=m.h;flashcardStart(h,'vocabulary','en-ja');h.elements.get('flashcard-reveal').listeners.click();
  const player=h.elements.get('flashcard-answer').children.at(-1);assert.equal(player.attributes['aria-label'],'Audio: Flashcard Japanese');
  player.children[0].children[0].listeners.click();assert.equal(m.spoken[0].text,'猫');assert.equal(m.spoken[0].lang,'ja-JP');
  const before=m.synth.cancels;h.elements.get('flashcard-next').listeners.click();assert.ok(m.synth.cancels>before);assert.equal(h.run('japaneseAudio.state().owner'),null);
  h.elements.get('flashcard-reveal').listeners.click();h.windowEvents.hashchange[0]();assert.equal(h.run('japaneseAudio.state().owner'),null);
});
test('flashcard audio handles missing Japanese voice without preventing reveal',()=>{
  const m=speechMock([{name:'English',lang:'en-US'}]),h=m.h;flashcardStart(h);h.run('japaneseAudio.refresh()');h.elements.get('flashcard-reveal').listeners.click();
  const player=h.elements.get('flashcard-answer').children.at(-1);assert.equal(player.children[0].children[0].disabled,true);assert.match(player.children.at(-1).textContent,/Japanese voices|No Japanese voice/);
  assert.equal(h.elements.get('flashcard-answer').hidden,false);assert.equal(m.spoken.length,0);
});
test('flashcard route and all session controls produce no AI, storage or review events',async()=>{
  const h=harness();h.run('appReady=true');h.ctx.location.hash='#study/flashcards';await h.run('renderRoute()');
  assert.equal(h.elements.get('flashcard-panel').hidden,false);assert.equal(h.elements.get('personalized-study').hidden,true);
  flashcardStart(h);for(const id of ['flashcard-reveal','flashcard-next','flashcard-prev','flashcard-shuffle','flashcard-restart','flashcard-finish','flashcard-again-shuffle'])h.elements.get(id).listeners.click();
  assert.equal(h.requests.length,0);assert.equal(h.storage.size,0);assert.equal(h.elements.get('flashcard-meter').attributes['aria-valuetext'],'Card 1 of 12');
});
test('return to ordinary Study preserves saved activity and existing routes',async()=>{
  const h=harness();h.run("appReady=true;placementLearnerId='example';studyPlan={session_id:'saved',status:'in_progress',activities:[],estimated_minutes:5,note:''};studyActivity={activity_id:'current'};refreshReviews=async()=>{}");
  h.elements.get('study-answer').value='先生です。';h.elements.get('study-activity').hidden=false;h.ctx.location.hash='#study/flashcards';await h.run('renderRoute()');
  h.ctx.location.hash='#study';await h.run('renderRoute()');assert.equal(h.elements.get('flashcard-panel').hidden,true);assert.equal(h.elements.get('study-answer').value,'先生です。');assert.equal(h.elements.get('study-activity').hidden,false);
});

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
  const h=harness({isSecureContext:true,mediaDevices,MediaRecorder:Recorder,Blob,URL:urls,now:()=>time,...config.audio});h.ctx.recorderDeps=deps;
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

function speechControllerMock(options={}) {
  const m=recordingMock(),uploads=[],timers=new Map();let sequence=0;
  const deps={recorder:m.recorder,prepare:options.prepare || (async()=>new Blob(['wav'],{type:'audio/wav'})),
    send:async(...args)=>{uploads.push(args);return options.send ? options.send(...args) : {language:'ja',provider:'groq',original_text:'こんにちは。'};},
    newId:()=>`request-${uploads.length+1}`,AbortType:AbortController,
    schedule:(fn)=>{timers.set(++sequence,fn);return sequence;},unschedule:id=>timers.delete(id)};
  m.h.ctx.speechDeps=deps;const controller=m.h.run('createSpeechTranscriber(speechDeps)');
  const preview=async()=>{await m.recorder.start();m.recorder.stop();m.recorders.at(-1).finish();};
  return {...m,controller,uploads,speechTimers:timers,preview};
}

test('speech WAV encoder emits bounded mono PCM16 with real frame duration',async()=>{
  const h=harness();h.ctx.samples=new Float32Array([-1,0,1,.5]);
  const wav=h.run('encodeSpeechWav(samples)');const data=new DataView(await wav.arrayBuffer());
  assert.equal(wav.type,'audio/wav');assert.equal(wav.size,52);assert.equal(data.getUint32(24,true),16000);assert.equal(data.getUint16(22,true),1);
  assert.equal(data.getInt16(44,true),-32768);assert.equal(data.getInt16(48,true),32767);assert.equal(data.getUint32(40,true),8);
  h.ctx.samples=new Float32Array(960001);assert.throws(()=>h.run('encodeSpeechWav(samples)'),/60 seconds/);
  h.ctx.samples=new Float32Array([NaN]);assert.throws(()=>h.run('encodeSpeechWav(samples)'),/could not be prepared/);
});

test('explicit transcription yields editable original and never sends a Tutor request',async()=>{
  const m=speechControllerMock();await m.preview();assert.equal(m.uploads.length,0);
  await m.controller.transcribe('learner');assert.equal(m.controller.state().original,'こんにちは。');
  m.controller.edit('こんにちは。ミゲルです。');let confirmed;
  m.controller.confirm(text=>{confirmed=text;});assert.equal(confirmed,'こんにちは。ミゲルです。');
  assert.equal(m.controller.state().original,'こんにちは。');assert.equal(m.uploads.length,1);assert.equal(m.h.requests.length,0);assert.equal(m.h.storage.size,0);
});

test('transcription requires a learner and a completed recording',async()=>{
  const m=speechControllerMock();await m.controller.transcribe('learner');assert.equal(m.uploads.length,0);
  await m.preview();await m.controller.transcribe(null);assert.match(m.controller.state().message,/learner profile/);assert.equal(m.uploads.length,0);
});

test('duplicate transcription clicks produce only one upload and failure retains preview for retry',async()=>{
  let finish;const m=speechControllerMock({send:()=>new Promise(resolve=>{finish=resolve;})});await m.preview();
  const first=m.controller.transcribe('learner');await Promise.resolve();await m.controller.transcribe('learner');assert.equal(m.uploads.length,1);
  finish({language:'ja',provider:'groq',original_text:'こんにちは。'});await first;assert.equal(m.recorder.state().phase,'preview');
  const n=speechControllerMock({send:async()=>{throw new TypeError('offline');}});await n.preview();await n.controller.transcribe('learner');
  assert.equal(n.controller.state().phase,'error');assert.match(n.controller.state().message,/still here/);assert.equal(n.recorder.state().phase,'preview');
  await n.controller.transcribe('learner');assert.equal(n.uploads.length,2);assert.equal(n.uploads[0][2],'request-1');assert.equal(n.uploads[1][2],'request-2');
});

test('discard during preparation prevents uploads and late completion cannot restore transcript',async()=>{
  let complete;const m=speechControllerMock({prepare:()=>new Promise(resolve=>{complete=resolve;})});await m.preview();
  const pending=m.controller.transcribe('learner');m.recorder.cancel();complete(new Blob(['wav']));await pending;
  assert.equal(m.uploads.length,0);assert.equal(m.controller.state().original,'');assert.equal(m.controller.state().phase,'idle');assert.equal(m.speechTimers.size,0);
});

test('cancel aborts upload and stale provider replies cannot populate a transcript',async()=>{
  let complete;const m=speechControllerMock({send:()=>new Promise(resolve=>{complete=resolve;})});await m.preview();
  const pending=m.controller.transcribe('learner');await new Promise(setImmediate);const signal=m.uploads[0][3];
  m.controller.cancel();assert.equal(signal.aborted,true);complete({language:'ja',provider:'groq',original_text:'こんにちは。'});await pending;
  assert.equal(m.controller.state().original,'');assert.equal(m.recorder.state().phase,'preview');assert.equal(m.speechTimers.size,0);
});

test('transcription deadline aborts the request but keeps the recording',async()=>{
  let complete;const m=speechControllerMock({send:()=>new Promise(resolve=>{complete=resolve;})});await m.preview();
  const pending=m.controller.transcribe('learner');await new Promise(setImmediate);[...m.speechTimers.values()][0]();
  assert.equal(m.controller.state().phase,'error');assert.equal(m.uploads[0][3].aborted,true);assert.equal(m.recorder.state().phase,'preview');
  complete({});await pending;assert.match(m.controller.state().message,/too long/);
});

test('bad provider responses are rejected and confirmation cannot erase a draft',async()=>{
  for(const result of [{language:'en',provider:'groq',original_text:'hello'},null,{language:'ja',provider:'groq',original_text:''}]){
    const m=speechControllerMock({send:async()=>result});await m.preview();await m.controller.transcribe('learner');assert.equal(m.controller.state().phase,'error');assert.equal(m.recorder.state().phase,'preview');
  }
  const m=speechControllerMock();await m.preview();await m.controller.transcribe('learner');m.controller.edit('');let applied=false;m.controller.confirm(()=>{applied=true;});assert.equal(applied,false);
});

function speechDecodeMock(h,{duration=.1,decodeFailure=null}={}) {
  let closed=0;const decoded={duration,numberOfChannels:1};
  class Context {constructor(){this.state='running';} async decodeAudioData(){if(decodeFailure)throw {name:decodeFailure};return decoded;} async close(){this.state='closed';closed++;}}
  class Offline {constructor(channels,frames,rate){assert.equal(channels,1);assert.equal(rate,16000);this.frames=frames;} createBufferSource(){return {connect(){},start(){}};} async startRendering(){return {getChannelData:()=>new Float32Array(this.frames).fill(.1)};}}
  h.ctx.window.AudioContext=Context;h.ctx.window.OfflineAudioContext=Offline;return ()=>closed;
}

test('browser normalization accepts native WebM, MP4 and Ogg recordings and closes decoding resources',async()=>{
  for(const mimeType of ['audio/webm;codecs=opus','audio/mp4','audio/ogg;codecs=opus']){
    const h=harness({Blob});const closes=speechDecodeMock(h);h.ctx.clip={blob:new Blob(['recording'],{type:mimeType}),durationMs:1};h.ctx.signal=new AbortController().signal;
    const wav=await h.run('prepareSpeechAudio(clip,signal)');assert.equal(wav.type,'audio/wav');assert.equal(wav.size,3244);assert.equal(closes(),1);
  }
});

test('normalization rejects undecodable, oversized or longer-than-sixty-second audio before upload',async()=>{
  const h=harness({Blob});h.ctx.clip={blob:new Blob(['recording']),durationMs:1};h.ctx.signal=new AbortController().signal;
  let closes=speechDecodeMock(h,{duration:61});await assert.rejects(h.run('prepareSpeechAudio(clip,signal)'),/60 seconds/);assert.equal(closes(),1);
  closes=speechDecodeMock(h,{decodeFailure:'EncodingError'});await assert.rejects(h.run('prepareSpeechAudio(clip,signal)'),/cannot decode/);assert.equal(closes(),1);
  h.ctx.clip={blob:new Blob(['x'.repeat(8*1024*1024+1)])};await assert.rejects(h.run('prepareSpeechAudio(clip,signal)'),/shorter/);assert.equal(h.requests.length,0);
});

test('real transcription UI copies edited text only on confirm and preserves composer drafts',async()=>{
  const m=recordingMock(),h=m.h;speechDecodeMock(h);h.run("placementLearnerId='learner'");
  h.ctx.fetch=async(url,options={})=>{h.requests.push({url,...options});return {ok:true,status:200,json:async()=>url==='/api/speech/config'?{enabled:true}:{language:'ja',provider:'groq',original_text:'こんにちは。'}};};
  await h.run('loadSpeechConfiguration()');await h.run('browserRecorder.start()');h.run('browserRecorder.stop()');m.recorders[0].finish();
  assert.equal(h.elements.get('speech-transcribe').disabled,false);await h.elements.get('speech-transcribe').listeners.click();
  assert.equal(h.elements.get('speech-transcript').value,'こんにちは。');assert.equal(h.elements.get('message').value,'');
  assert.equal(h.elements.get('speech-transcribe').disabled,true);assert.equal(h.elements.get('speech-transcribe').textContent,'Transcribed');
  h.elements.get('speech-transcript').value='ミゲルです。';h.elements.get('speech-transcript').listeners.input();
  h.elements.get('message').value='Existing draft';h.elements.get('speech-confirm').listeners.click();assert.equal(h.elements.get('message').value,'Existing draft');
  h.elements.get('message').value='';h.elements.get('speech-confirm').listeners.click();assert.equal(h.elements.get('message').value,'ミゲルです。');assert.equal(h.elements.get('speech-original').textContent,'こんにちは。');
  assert.equal(h.requests.filter(r=>r.url.endsWith('/speech/transcribe')).length,1);assert.equal(h.requests.some(r=>r.url==='/api/chat'),false);assert.equal(h.storage.size,0);
  h.run('browserRecorder.cancel()');assert.equal(h.elements.get('speech-result').hidden,true);assert.equal(h.elements.get('speech-transcript').value,'');
});

test('disabled configuration blocks uploads while local recorder remains usable',async()=>{
  const m=recordingMock(),h=m.h;h.ctx.fetch=async()=>({ok:true,status:200,json:async()=>({enabled:false,setup_message:'Disabled'})});
  await h.run('loadSpeechConfiguration()');await h.run('browserRecorder.start()');h.run('browserRecorder.stop()');m.recorders[0].finish();
  assert.equal(h.elements.get('speech-transcribe').disabled,true);assert.equal(h.elements.get('recording-play').hidden,false);assert.equal(h.elements.get('speech-config-status').textContent,'Disabled');
});

async function speakingHarness(level='Beginner',mode='read',config={}) {
  const m=recordingMock(config),h=m.h;speechDecodeMock(h);h.run("placementLearnerId='learner';appReady=true");h.ctx.location.hash='#study/speaking';
  h.elements.get('speaking-level').value=level;h.elements.get('speaking-mode').value=mode;
  h.ctx.fetch=async(url,options={})=>{h.requests.push({url,...options});return {ok:true,status:200,json:async()=>url==='/api/speech/config'?{enabled:true}:{language:'ja',provider:'groq',original_text:'こんにちは。'}};};
  await h.run('renderRoute()');h.elements.get('speaking-start').listeners.click();return m;
}
async function speakingTranscript(m,text='こんにちは。') {
  const h=m.h;await h.run('loadSpeechConfiguration()');await h.run('browserRecorder.start()');h.run('browserRecorder.stop()');m.recorders.at(-1).finish();
  await h.elements.get('speech-transcribe').listeners.click();h.elements.get('speech-transcript').value=text;h.elements.get('speech-transcript').listeners.input();
}

test('speaking catalog provides two original exercises for all three modes at each level',()=>{
  const h=harness(),exercises=h.run('speakingExercises');assert.equal(exercises.length,18);assert.equal(new Set(exercises.map(e=>e.id)).size,18);
  for(const level of ['Beginner','N5','N4'])for(const mode of ['read','answer','repeat']){
    const set=exercises.filter(e=>e.level===level&&e.mode===mode);assert.equal(set.length,2);for(const exercise of set){assert.match(exercise.prompt,/[ぁ-んァ-ヶ一-龯]/);assert.ok(exercise.note);if(mode==='answer')assert.ok(exercise.sample);}
  }
});

test('Study speaking loads without generation and moves the single recorder instead of duplicating it',async()=>{
  const m=await speakingHarness(),h=m.h;assert.equal(h.elements.get('speaking-panel').hidden,false);assert.equal(h.elements.get('personalized-study').hidden,true);
  assert.equal(h.elements.get('recording-card').parentElement,h.elements.get('speaking-recording-slot'));assert.equal(h.elements.get('speech-confirm').textContent,'Confirm answer');
  assert.equal(m.requests.length,0);assert.equal(h.requests.filter(r=>!r.url.includes('/audio/attempts')).length,0);assert.equal(h.run('speakingState.exercises.length'),2);
  assert.equal(h.elements.get('speaking-next').disabled,true);assert.equal(h.elements.get('speaking-feedback').hidden,true);
});

test('Read Aloud waits for explicit confirmation and keeps original, edited and reference text separate',async()=>{
  const m=await speakingHarness(),h=m.h;await speakingTranscript(m,'こんにちは！');
  assert.equal(h.elements.get('speaking-feedback').hidden,true);assert.equal(h.run('speakingState.confirmed'),null);
  await h.elements.get('speech-confirm').listeners.click();assert.equal(h.elements.get('speaking-feedback').hidden,false);assert.match(h.elements.get('speaking-feedback-text').textContent,/matches the reference/);
  assert.equal(h.run('speakingState.confirmed.original'),'こんにちは。');assert.equal(h.run('speakingState.confirmed.text'),'こんにちは！');assert.equal(h.run('speakingState.confirmed.reference'),'こんにちは。');
  assert.equal(h.elements.get('message').value,'');assert.equal(h.requests.some(r=>r.url==='/api/chat'||r.url.includes('/mastery')),false);
});

test('duplicate confirmation reuses feedback; edits require fresh explicit confirmation',async()=>{
  const m=await speakingHarness(),h=m.h;await speakingTranscript(m);await h.elements.get('speech-confirm').listeners.click();const previous=h.run('speakingState.lastEvaluation');
  const requests=h.requests.length;await h.elements.get('speech-confirm').listeners.click();assert.equal(h.requests.length,requests);assert.equal(h.run('speakingState.lastEvaluation.feedback'),previous.feedback);
  h.elements.get('speech-transcript').value='今日はいい天気ですね。';h.elements.get('speech-transcript').listeners.input();assert.equal(h.elements.get('speaking-feedback').hidden,true);assert.equal(h.elements.get('speaking-next').disabled,true);
  await h.elements.get('speech-confirm').listeners.click();assert.match(h.elements.get('speaking-feedback-text').textContent,/differs from the reference/);assert.equal(h.elements.get('speaking-next').disabled,false);
});

test('Spoken Answer recognizes reviewed alternatives and unknown valid expressions stay neutral',async()=>{
  const m=await speakingHarness('N5','answer'),h=m.h;await speakingTranscript(m,'ふたつです。');await h.elements.get('speech-confirm').listeners.click();assert.match(h.elements.get('speaking-feedback-text').textContent,/matches a reviewed answer/);
  const exercise=h.run('speakingCurrent()');h.ctx.exercise=exercise;
  for(const text of exercise.accepted){h.ctx.text=text;assert.match(h.run('speakingFeedback(exercise,text)'),/matches a reviewed answer/);}
  h.ctx.text='りんごは二個あります。';assert.match(h.run('speakingFeedback(exercise,text)'),/not marked wrong/);
  assert.equal(h.elements.get('speaking-reference-label').textContent,'One possible answer');assert.equal(h.elements.get('message').value,'');
});

test('open Spoken Answers offer conservative pattern feedback rather than correctness verdicts',()=>{
  const h=harness();
  for(const [id,text,pattern] of [['beginner-answer-name','私の名前はミゲルです。',/self-introduction/],['n4-answer-yesterday','昨日は本を読みました。',/polite past ending/],['n4-answer-weekend','図書館に行くつもりです。',/planning expression/]]){
    h.ctx.id=id;h.ctx.text=text;assert.match(h.run('speakingFeedback(speakingExercises.find(e=>e.id===id),text)'),pattern);
  }
});

test('Repeat Phrase requires reference playback or assisted reveal; no pronunciation score is fabricated',async()=>{
  const m=await speakingHarness('Beginner','repeat'),h=m.h;assert.equal(h.elements.get('speaking-prompt').hidden,true);
  await speakingTranscript(m,'すみません。');await h.elements.get('speech-confirm').listeners.click();assert.equal(h.elements.get('speaking-feedback').hidden,true);assert.match(h.elements.get('speech-status').textContent,/Listen/);
  h.elements.get('speaking-reveal').listeners.click();await h.elements.get('speech-confirm').listeners.click();assert.equal(h.elements.get('speaking-feedback').hidden,false);assert.match(h.elements.get('speaking-feedback-text').textContent,/not a pronunciation score/);assert.doesNotMatch(h.elements.get('speaking-feedback-text').textContent,/\d+%/);
});

test('reference TTS uses the existing controller and stops before recording without losing the exercise',async()=>{
  const speech=speechMock(),m=await speakingHarness('N5','repeat',{audio:{speechSynthesis:speech.synth,SpeechSynthesisUtterance:speech.Utterance}}),h=m.h;
  const player=h.elements.get('speaking-audio').children[0];player.children[0].children[0].listeners.click();speech.spoken.at(-1).onstart();assert.equal(h.run('speakingState.heard'),true);
  const id=h.run('speakingCurrent().id');await h.run('browserRecorder.start()');assert.equal(h.run('japaneseAudio.state().owner'),null);assert.equal(h.run('japaneseAudio.state().blocked'),true);assert.equal(h.run('speakingCurrent().id'),id);
});

test('exercise progression requires confirmation and releases recording resources on next/retry/end',async()=>{
  const m=await speakingHarness('N4','read'),h=m.h;h.elements.get('speaking-next').listeners.click();assert.equal(h.run('speakingState.index'),0);
  await speakingTranscript(m,h.run('speakingCurrent().prompt'));await h.elements.get('speech-confirm').listeners.click();h.elements.get('speaking-next').listeners.click();
  assert.equal(h.run('speakingState.index'),1);assert.equal(h.run('browserRecorder.state().phase'),'idle');assert.equal(h.run('speechTranscriber.state().original'),'');assert.equal(m.revoked.length,1);
  const exercise=h.run('speakingCurrent().id');h.elements.get('speaking-retry').listeners.click();assert.equal(h.run('speakingCurrent().id'),exercise);assert.equal(h.elements.get('speaking-next').disabled,true);
  await speakingTranscript(m,h.run('speakingCurrent().prompt'));await h.elements.get('speech-confirm').listeners.click();h.elements.get('speaking-next').listeners.click();assert.equal(h.run('speakingState'),null);assert.match(h.elements.get('speaking-notice').textContent,/finished/);
  assert.equal(h.elements.get('recording-card').parentElement,h.elements.get('tutor-recording-slot'));assert.equal(h.elements.get('speech-confirm').textContent,'Confirm text');
});

test('speaking microphone denial leaves the exercise and existing retry controls usable',async()=>{
  const m=await speakingHarness('Beginner','read',{denied:'NotAllowedError'}),h=m.h;const id=h.run('speakingCurrent().id');await h.run('browserRecorder.start()');
  assert.equal(h.run('browserRecorder.state().phase'),'error');assert.match(h.elements.get('recording-error').textContent,/permission was denied/);assert.equal(h.run('speakingCurrent().id'),id);assert.equal(h.elements.get('speaking-feedback').hidden,true);
  h.elements.get('speaking-retry').listeners.click();assert.equal(h.run('browserRecorder.state().phase'),'idle');assert.equal(h.requests.filter(r=>!r.url.includes('/audio/attempts')).length,0);
});

test('speaking transcription failures retain the preview and cannot evaluate unconfirmed output',async()=>{
  const m=await speakingHarness(),h=m.h;await h.run('loadSpeechConfiguration()');h.ctx.fetch=async()=>{throw new TypeError('offline');};
  await h.run('browserRecorder.start()');h.run('browserRecorder.stop()');m.recorders[0].finish();await h.elements.get('speech-transcribe').listeners.click();
  assert.equal(h.run('browserRecorder.state().phase'),'preview');assert.equal(h.run('speechTranscriber.state().phase'),'error');assert.equal(h.elements.get('speaking-feedback').hidden,true);await h.elements.get('speech-confirm').listeners.click();assert.equal(h.run('speakingState.confirmed'),null);
});

test('leaving speaking cleans capture/transcripts and restores the Tutor confirmation target',async()=>{
  const m=await speakingHarness(),h=m.h;await h.run('browserRecorder.start()');
  h.ctx.location.hash='#home';for(const fn of h.windowEvents.hashchange)if(fn.name!=='renderRoute')fn();h.run('speakingRoute(false)');
  assert.equal(m.tracks[0].stops,1);assert.equal(h.run('browserRecorder.state().phase'),'idle');assert.equal(h.run('speechTranscriber.state().original'),'');assert.equal(h.elements.get('recording-card').parentElement,h.elements.get('tutor-recording-slot'));
  assert.equal(h.elements.get('speech-confirm').textContent,'Confirm text');assert.equal(h.run('speakingState.index'),0);assert.equal(h.requests.filter(r=>!r.url.includes('/audio/attempts')).length,0);
});
async function voiceHarness(config={}) {
  const m=recordingMock(config),h=m.h;speechDecodeMock(h);
  h.ctx.practiceFixture=practice;
  h.run("placementLearnerId='learner';sessionId='practice';savedSession=true;appReady=true;$('tutor-panel').hidden=false;applyPractice(practiceFixture)");
  h.ctx.location.hash='#tutor';h.elements.get('level').value='beginner';
  const response={message:'かしこまりました。こちらへどうぞ。',evaluation:null,correction:null,explanation:null,examples:[],exercise:null};
  respond(h,url=>url==='/api/speech/config'?{enabled:true}:url.includes('/speech/transcribe')?{language:'ja',provider:'groq',original_text:'一人です。'}:url==='/api/chat'?{response}:{conversation:practice});
  await h.run('loadSpeechConfiguration()');return m;
}
async function voiceTranscript(m,text='二人です。') {
  const h=m.h;await h.elements.get('recording-start').listeners.click();h.elements.get('recording-stop').listeners.click();m.recorders.at(-1).finish();
  await h.elements.get('speech-transcribe').listeners.click();h.elements.get('speech-transcript').value=text;h.elements.get('speech-transcript').listeners.input();
}
const chatRequests=h=>h.requests.filter(r=>r.url==='/api/chat');

test('voice is an optional active-scenario input; only confirmed edited text enters the same chat endpoint',async()=>{
  const m=await voiceHarness(),h=m.h;assert.equal(h.elements.get('recording-start').textContent,'Record Reply');assert.equal(h.elements.get('speech-confirm').textContent,'Confirm and Send');
  await voiceTranscript(m);assert.equal(chatRequests(h).length,0);assert.equal(h.run('speechTranscriber.state().original'),'一人です。');assert.equal(h.elements.get('message').value,'');
  h.elements.get('speech-confirm').listeners.click();await h.run('voiceSendTask');
  assert.equal(chatRequests(h).length,1);const payload=JSON.parse(chatRequests(h)[0].body);assert.equal(payload.message,'二人です。');assert.equal(payload.session_id,'practice');assert.equal(payload.learner_id,'learner');assert.ok(payload.request_id);
  assert.equal(h.elements.get('conversation').children.filter(c=>c.className==='message learner').length,1);assert.equal(h.run('speechTranscriber.state().original'),'');assert.equal(h.run('browserRecorder.recording()'),null);assert.equal(h.run('practiceState.effective_level'),'N5');
});

test('double voice and text submissions while a reply is pending issue one generation request',async()=>{
  const m=await voiceHarness(),h=m.h;await voiceTranscript(m);let finish;
  h.ctx.fetch=async(url,options={})=>{h.requests.push({url,...options});if(url==='/api/chat')await new Promise(resolve=>finish=resolve);return {ok:true,status:200,json:async()=>url==='/api/chat'?{response:{message:'どうぞ。',examples:[],exercise:null}}:{conversation:practice}};};
  h.elements.get('speech-confirm').listeners.click();h.elements.get('speech-confirm').listeners.click();await h.run('submitChatMessage()');assert.equal(chatRequests(h).length,1);assert.equal(h.elements.get('recording-start').disabled,true);finish();await h.run('voiceSendTask');assert.equal(chatRequests(h).length,1);
});

test('voice generation failure retains transcript and retries the same request ID without retranscribing',async()=>{
  const m=await voiceHarness(),h=m.h;await voiceTranscript(m);let fail=true;const base=h.ctx.fetch;
  h.ctx.fetch=async(url,options={})=>{if(url==='/api/chat'&&fail){h.requests.push({url,...options});throw new TypeError('lost response');}return base(url,options);};
  h.elements.get('speech-confirm').listeners.click();await h.run('voiceSendTask');assert.equal(h.elements.get('message').value,'二人です。');assert.equal(h.run('speechTranscriber.state().edited'),'二人です。');assert.equal(h.run('browserRecorder.state().phase'),'preview');
  fail=false;h.elements.get('speech-confirm').listeners.click();await h.run('voiceSendTask');assert.equal(JSON.parse(chatRequests(h)[0].body).request_id,JSON.parse(chatRequests(h)[1].body).request_id);assert.equal(h.requests.filter(r=>r.url.includes('/speech/transcribe')).length,1);
});

test('typed drafts are protected; switching to text preserves scenario and cancels old voice resources on success',async()=>{
  const m=await voiceHarness(),h=m.h;await voiceTranscript(m);h.elements.get('message').value='水をください。';h.elements.get('speech-confirm').listeners.click();assert.equal(chatRequests(h).length,0);assert.match(h.run('speechTranscriber.state().message'),/different reply/);
  await h.run('submitChatMessage()');assert.equal(JSON.parse(chatRequests(h)[0].body).message,'水をください。');assert.equal(h.run('sessionId'),'practice');assert.equal(h.run('practiceState.correction_policy'),'balanced');assert.equal(h.run('browserRecorder.recording()'),null);
  await voiceTranscript(m);h.elements.get('speech-confirm').listeners.click();await h.run('voiceSendTask');assert.equal(chatRequests(h).length,2);
});

test('stale transcription after a session change cannot send into the new conversation',async()=>{
  const m=await voiceHarness(),h=m.h;let finish;const base=h.ctx.fetch;
  h.ctx.fetch=async(url,options)=>url.includes('/speech/transcribe')?new Promise(resolve=>finish=()=>resolve({ok:true,status:200,json:async()=>({language:'ja',provider:'groq',original_text:'二人です。'})})):base(url,options);
  await h.elements.get('recording-start').listeners.click();h.elements.get('recording-stop').listeners.click();m.recorders.at(-1).finish();const pending=h.elements.get('speech-transcribe').listeners.click();await new Promise(resolve=>setImmediate(resolve));
  h.run("sessionId='other';applyPractice({...practiceFixture,session_id:'other'})");finish();await pending;assert.equal(h.run('speechTranscriber.state().original'),'');h.elements.get('speech-confirm').listeners.click();assert.equal(chatRequests(h).length,0);
});

test('navigation during transcription invalidates voice context; recorder tracks and local URLs are released',async()=>{
  const m=await voiceHarness(),h=m.h;await voiceTranscript(m);for(const fn of h.windowEvents.hashchange)fn();assert.equal(h.run('voiceReplyTarget'),null);assert.equal(h.run('browserRecorder.recording()'),null);assert.equal(h.run('speechTranscriber.state().original'),'');assert.equal(m.tracks[0].stops,1);assert.ok(m.revoked.length);
});

test('finish during recording releases the microphone and prevents sending to a completed scenario',async()=>{
  const m=await voiceHarness(),h=m.h;await h.elements.get('recording-start').listeners.click();h.ctx.completed={...practice,status:'completed',recap:{turn_count:0,final_effective_level:'N5',topics:[],observations:0,recent_performance_average:null,scored_turns:0}};respond(h,()=>h.ctx.completed);
  await h.elements.get('practice-finish').listeners.click();assert.equal(m.tracks[0].stops,1);assert.equal(h.run('browserRecorder.state().phase'),'idle');assert.equal(h.elements.get('recording-card').hidden,true);assert.equal(h.run("confirmVoiceReply('二人です。')").includes('no longer'),true);assert.equal(chatRequests(h).length,0);
});

test('voice permission denial and STT failure retain the active scenario and allow explicit retry',async()=>{
  const denied=await voiceHarness({denied:'NotAllowedError'});await denied.h.elements.get('recording-start').listeners.click();assert.equal(denied.h.run('browserRecorder.state().phase'),'error');assert.equal(denied.h.run('practiceState.status'),'active');
  const m=await voiceHarness(),h=m.h;let fail=true;const base=h.ctx.fetch;h.ctx.fetch=async(url,options)=>{if(url.includes('/speech/transcribe')&&fail)throw new TypeError('offline');return base(url,options);};
  await voiceTranscript(m);assert.equal(h.run('speechTranscriber.state().phase'),'error');assert.equal(h.run('practiceState.status'),'active');assert.equal(chatRequests(h).length,0);fail=false;await h.elements.get('speech-transcribe').listeners.click();assert.equal(h.run('speechTranscriber.state().phase'),'editing');
});

test('reload restores a single authored opening and saved confirmed turns with playback but no generation',async()=>{
  const speech=speechMock(),h=speech.h;h.ctx.saved={...practiceSaved,turns:[{message:'二人です。',response:{message:'こちらへどうぞ。',examples:[],exercise:null}}],interaction_count:1};h.run("placementLearnerId='learner';$('tutor-panel').hidden=false");respond(h,()=>h.ctx.saved);
  await h.run("openSavedSession('practice')");assert.equal(h.elements.get('conversation').children.length,3);assert.equal(h.run('practiceState.status'),'active');assert.equal(h.elements.get('speech-confirm').textContent,'Confirm and Send');
  h.elements.get('conversation').children[0].children.at(-1).children[0].children[0].listeners.click();assert.match(speech.spoken.at(-1).text,/何名様/);h.elements.get('conversation').children[2].children.at(-1).children[0].children[0].listeners.click();assert.match(speech.spoken.at(-1).text,/こちらへ/);assert.equal(chatRequests(h).length,0);
});

test('cancel voice keeps the typed draft and scenario; general Tutor and Study confirmation remain separate',async()=>{
  const m=await voiceHarness(),h=m.h;await voiceTranscript(m);h.elements.get('message').value='水をください。';h.elements.get('voice-reply-cancel').listeners.click();assert.equal(h.elements.get('message').value,'水をください。');assert.equal(h.run('sessionId'),'practice');assert.equal(h.run('voiceReplyTarget'),null);
  h.run('applyPractice(null)');assert.equal(h.elements.get('speech-confirm').textContent,'Confirm text');assert.equal(h.elements.get('recording-summary').textContent,'Record spoken Japanese');
});

test('late chat response after a learner/session switch cannot populate the replacement conversation',async()=>{
  const m=await voiceHarness(),h=m.h;await voiceTranscript(m);let finish;h.ctx.fetch=async(url,options={})=>{h.requests.push({url,...options});await new Promise(resolve=>finish=resolve);return {ok:true,status:200,json:async()=>({response:{message:'どうぞ。',examples:[],exercise:null}})};};
  h.elements.get('speech-confirm').listeners.click();h.run("sessionId='replacement';placementLearnerId='other';applyPractice(null)");finish();await h.run('voiceSendTask');assert.equal(h.elements.get('conversation').children.length,0);assert.equal(h.run('voiceReplyTarget'),null);assert.equal(h.run('speechTranscriber.state().original'),'');
});

test('completed scenario does not block the separate Study speaking recorder',async()=>{
  const m=await voiceHarness(),h=m.h;h.run("applyPractice({...practiceFixture,status:'completed'})");h.ctx.location.hash='#study/speaking';h.elements.get('speaking-level').value='Beginner';h.elements.get('speaking-mode').value='read';await h.run('renderRoute()');h.elements.get('speaking-start').listeners.click();await h.elements.get('recording-start').listeners.click();assert.equal(h.run('browserRecorder.state().phase'),'recording');assert.equal(h.elements.get('recording-card').hidden,false);assert.equal(h.elements.get('speech-confirm').textContent,'Confirm answer');assert.equal(chatRequests(h).length,0);
});

test('audio server catalog matches authored frontend exercises',()=>{
  const h=harness(),catalog=JSON.parse(fs.readFileSync(path.join(root,'..','app','audio_progress','catalog.json'),'utf8'));
  assert.deepEqual(JSON.parse(JSON.stringify(h.run('listeningExercises'))),catalog.listening);
  assert.deepEqual(JSON.parse(JSON.stringify(h.run('speakingExercises.map(({id,level,mode})=>({id,level,mode}))'))),catalog.speaking);
});
test('listening playback alone creates no completed activity; server determines saved correctness',async()=>{
  const h=harness();h.run("placementLearnerId='learner'");respond(h,url=>url.endsWith('/complete')?{correct:false}:{});
  h.elements.get('listening-level').value='N5';h.elements.get('listening-start').listeners.click();
  assert.equal(h.requests.filter(r=>r.url.endsWith('/complete')).length,0);
  h.run('listeningState.heard=true');h.elements.get('listening-choices').selected={value:'1'};
  await h.elements.get('listening-answer-form').listeners.submit({preventDefault(){}});
  assert.equal(h.run('listeningState.results[0].correct'),false);assert.match(h.elements.get('listening-feedback').textContent,/Answer/);
  await h.elements.get('listening-answer-form').listeners.submit({preventDefault(){}});
  assert.equal(h.requests.filter(r=>r.url.endsWith('/complete')).length,1);
});
test('uncertain listening save retains attempt ID and first answer across retry',async()=>{
  const h=harness();h.run("placementLearnerId='learner'");let fail=true;respond(h,()=>({}));const base=h.ctx.fetch;
  h.ctx.fetch=async(url,options)=>{if(url.endsWith('/complete')&&fail){h.requests.push({url,...options});throw new TypeError('offline');}return base(url,options);};
  h.elements.get('listening-level').value='N5';h.elements.get('listening-start').listeners.click();h.run('listeningState.heard=true');h.elements.get('listening-choices').selected={value:'1'};
  await h.elements.get('listening-answer-form').listeners.submit({preventDefault(){}});assert.equal(h.run('listeningState.answered'),false);
  h.elements.get('listening-choices').selected={value:'0'};fail=false;await h.elements.get('listening-answer-form').listeners.submit({preventDefault(){}});
  const saves=h.requests.filter(r=>r.url.endsWith('/complete'));assert.equal(saves[0].url,saves[1].url);assert.equal(saves[0].body,saves[1].body);
});
test('speaking saves confirmed metadata only, never original or edited transcript',async()=>{
  const m=await speakingHarness(),h=m.h;await speakingTranscript(m,'ミゲルです。');await h.elements.get('speech-confirm').listeners.click();
  const saves=h.requests.filter(r=>r.url.endsWith('/complete'));assert.equal(saves.length,1);const payload=JSON.parse(saves[0].body);assert.ok(payload.transcription_id);assert.equal(payload.assisted,false);assert.doesNotMatch(saves[0].body,/ミゲル|こんにちは/);
  await h.elements.get('speech-confirm').listeners.click();assert.equal(h.requests.filter(r=>r.url.endsWith('/complete')).length,1);
});
test('failed speaking save retains confirmation controls and retries the same identity',async()=>{
  const m=await speakingHarness(),h=m.h;await speakingTranscript(m);let fail=true;const base=h.ctx.fetch;
  h.ctx.fetch=async(url,options)=>{if(url.endsWith('/complete')&&fail){h.requests.push({url,...options});throw new TypeError('offline');}return base(url,options);};
  await h.elements.get('speech-confirm').listeners.click();assert.equal(h.run('speakingState.confirmed'),null);assert.equal(h.elements.get('speaking-next').disabled,true);
  fail=false;await h.elements.get('speech-confirm').listeners.click();const saves=h.requests.filter(r=>r.url.endsWith('/complete'));assert.equal(saves[0].url,saves[1].url);assert.equal(h.elements.get('speaking-next').disabled,false);
});
const audioData={listening:{attempts:2,unassisted:{completed:2,correct:1,accuracy:50},assisted:{completed:0,correct:0,accuracy:null}},speaking:{read:{attempts:1,completed:1},answer:{attempts:0,completed:0},repeat:{attempts:0,completed:0}},voice:{completed_conversations:1,confirmed_turns:2},recent:[]};
function allText(element){return [element.textContent,...element.children.map(allText)].join(' ');}
test('audio progress renders separate activity and listening accuracy without provider requests',async()=>{
  const h=harness();h.run("placementLearnerId='learner'");respond(h,()=>audioData);await h.run("renderAudioProgress('learner')");
  const text=allText(h.elements.get('audio-progress'));assert.match(text,/50%/);assert.match(text,/Assisted: 0 correct/);assert.match(text,/Read Aloud: 1 attempts/);assert.match(text,/Completed conversations: 1/);assert.equal(h.requests.length,1);assert.equal(h.requests[0].url,'/api/learners/learner/audio/progress');
  h.run("progressSection('skills')");assert.equal(h.elements.get('audio-progress').hidden,true);h.run("progressSection('overview')");assert.equal(h.elements.get('audio-progress').hidden,false);
});
test('audio progress empty, error, retry and stale learner states are safe',async()=>{
  const h=harness();h.run("placementLearnerId='learner'");const empty=JSON.parse(JSON.stringify(audioData));empty.listening.attempts=0;for(const m of Object.values(empty.speaking)){m.attempts=0;m.completed=0;}empty.voice.confirmed_turns=0;respond(h,()=>empty);
  await h.run("renderAudioProgress('learner')");assert.match(allText(h.elements.get('audio-progress')),/after your first practice session/);
  h.ctx.fetch=async()=>{throw new TypeError('offline');};await h.run("renderAudioProgress('learner')");assert.match(allText(h.elements.get('audio-progress')),/other progress is still available/);
  respond(h,()=>audioData);await h.elements.get('audio-progress').children.at(-1).listeners.click();assert.match(allText(h.elements.get('audio-progress')),/50%/);
});
test('voice marker requires confirmed draft; ordinary typed scenario turns stay text',async()=>{
  const m=await voiceHarness(),h=m.h;await voiceTranscript(m);h.elements.get('message').value='水をください。';await h.run('submitChatMessage()');assert.equal(JSON.parse(chatRequests(h)[0].body).transcription_id,undefined);
  await voiceTranscript(m);h.elements.get('speech-confirm').listeners.click();await h.run('voiceSendTask');assert.ok(JSON.parse(chatRequests(h)[1].body).transcription_id);
});

test('partial speech engines degrade gracefully and explicit play resumes a paused engine',()=>{
  const m=speechMock();let resumed=0;m.synth.paused=true;m.synth.resume=()=>{resumed++;m.synth.paused=false;};
  assert.equal(m.h.run("japaneseAudio.play('こんにちは。','test')"),true);assert.equal(resumed,1);
  const h=harness({speechSynthesis:{getVoices(){return [];}},SpeechSynthesisUtterance:m.Utterance});
  assert.equal(h.run('japaneseAudio.state().availability'),'unsupported');assert.equal(h.run("japaneseAudio.play('日本語','test')"),false);
});

test('confirmation blocks duplicate work, recovers failures and ignores stale completion',async()=>{
  const m=speechControllerMock();await m.preview();await m.controller.transcribe('learner');let finish,calls=0;
  const pending=m.controller.confirm(()=>{calls++;return new Promise(resolve=>finish=resolve);});
  m.controller.confirm(()=>calls++);assert.equal(calls,1);assert.equal(m.controller.state().confirming,true);
  finish('');await pending;assert.equal(m.controller.state().confirming,false);
  await m.controller.confirm(()=>Promise.reject(new Error('offline')));assert.match(m.controller.state().message,/please retry/);assert.equal(m.controller.state().original,'こんにちは。');
  const stale=m.controller.confirm(()=>new Promise(resolve=>finish=resolve));m.controller.reset();finish('late');await stale;
  assert.equal(m.controller.state().original,'');assert.equal(m.controller.state().message,'');
});

test('enabled transcription configuration is cached, failed checks remain retryable',async()=>{
  const h=harness();h.ctx.fetch=async()=>{throw new TypeError('offline');};await h.run('loadSpeechConfiguration()');assert.equal(h.elements.get('speech-config-retry').hidden,false);
  respond(h,()=>({enabled:true}));await h.run('loadSpeechConfiguration()');await h.run('loadSpeechConfiguration()');assert.equal(h.requests.length,1);
});

test('prefixed Web Audio decoding works without autoplay or permanent recording storage',async()=>{
  const h=harness({Blob});const closes=speechDecodeMock(h);h.ctx.window.webkitAudioContext=h.ctx.window.AudioContext;h.ctx.window.webkitOfflineAudioContext=h.ctx.window.OfflineAudioContext;delete h.ctx.window.AudioContext;delete h.ctx.window.OfflineAudioContext;
  h.ctx.clip={blob:new Blob(['recording'],{type:'audio/mp4'})};h.ctx.signal=new AbortController().signal;
  const wav=await h.run('prepareSpeechAudio(clip,signal)');assert.equal(wav.type,'audio/wav');assert.equal(closes(),1);assert.equal(h.storage.size,0);
});
