const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const test = require('node:test');
const assert = require('node:assert/strict');
const root = path.join(__dirname, '..', 'frontend');
const html = fs.readFileSync(path.join(root, 'index.html'), 'utf8');
const scripts = [...html.matchAll(/src="\/static\/([^\"]+\.js)"/g)].map(m => m[1]);
function harness() {
  const elements = new Map(); const requests = []; const storage = new Map();
  class Element {
    constructor(tag = 'div') { this.tagName=tag; this.children=[]; this.listeners={}; this.hidden=false; this.value=''; this.textContent=''; this.attributes={}; }
    append(...children) { this.children.push(...children); }
    replaceChildren(...children) { this.children=children; this.textContent=''; }
    cloneNode() { return new Element(this.tagName); }
    get firstElementChild() { return this.children[0] || new Element(); }
    get childElementCount() { return this.children.length; }
    setAttribute(k,v) { this.attributes[k]=v; }
    addEventListener(type, fn) { this.listeners[type]=fn; }
    querySelectorAll() { return []; }
    closest() { return null; }
    focus() { this.focused=true; }
  }
  for (const m of html.matchAll(/<([\w-]+)\b[^>]*\bid="([^"]+)"[^>]*>/g)) { const e=new Element(m[1]); e.hidden=/\bhidden\b/.test(m[0]); elements.set(m[2],e); }
  elements.get('review-minutes').value='10'; elements.get('onboarding-goal-select').value='general';
  const ctx = vm.createContext({console, Event, URLSearchParams, Intl, TypeError, SyntaxError, crypto:require('node:crypto').webcrypto,
    document:{getElementById:id=>elements.get(id),createElement:tag=>new Element(tag),querySelectorAll:()=>[],querySelector:selector=>selector==='.skip-link'?new Element('a'):null,addEventListener(){},dispatchEvent(){}},
    window:{addEventListener(){},location:{assign(url){ctx.redirect=url;}}},location:{hash:''},navigator:{onLine:true},
    localStorage:{getItem:k=>storage.get(k)||null,setItem:(k,v)=>storage.set(k,v),removeItem:k=>storage.delete(k)},
    sessionStorage:{getItem:()=>null,setItem(){}},
    fetch:async (url, options={})=>{ requests.push({url,...options}); throw new TypeError('offline'); }
  });
  // Run all real scripts; bootstrap is invoked explicitly by each test.
  for (const name of scripts) { let source=fs.readFileSync(path.join(root,name),'utf8'); if(name==='shell.js') source=source.replace(/boot\(\);\s*$/, ''); vm.runInContext(source,ctx,{filename:name}); }
  return {ctx,elements,requests,storage,run:source=>vm.runInContext(source,ctx)};
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
