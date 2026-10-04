const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const root = path.join(__dirname, '..', 'frontend');
const html = fs.readFileSync(path.join(root, 'account.html'), 'utf8');
const source = fs.readFileSync(path.join(root, 'account.js'), 'utf8');
const tick = async () => { for (let i = 0; i < 5; i++) await new Promise(setImmediate); };

function harness({ state, pathname = '/auth/sign-in', hash = '', bootstrapError } = {}) {
  const nodes = new Map(), events = {}, requests = [], notices = [];
  const node = (tag, attrs='') => ({ tag, hidden: /\bhidden\b/.test(attrs), value: '', textContent: '', listeners: {}, disabled:false,
    addEventListener(event, fn) { this.listeners[event] = fn; }, setAttribute(k,v) { this[k]=v; }, removeAttribute(k) { delete this[k]; }, focus() { this.focused=true; } });
  for (const match of html.matchAll(/<([\w-]+)\b([^>]*\bid="([^"]+)"[^>]*)>/g)) nodes.set(match[3],node(match[1],match[2]));
  const navigation = ['login','invite','forgot','reset'].map(screen => { const button=node('button');button.dataset={screen};return button; });
  const buttons=[...Array.from(nodes.values()).filter(n=>n.tag==='button'),...navigation];
  const passwords=['login-password','email-link','new-password','confirm-password','gate-code'].map(id=>nodes.get(id));
  let reply;
  const ctx={document:{getElementById:id=>nodes.get(id),querySelectorAll(selector){
    if(selector==='input[type="password"]')return passwords;
    if(selector==='[data-screen]')return navigation;
    return buttons;
  }},location:{pathname,hash,search:'',reload(){notices.push('reload');}},history:{replaceState(...args){notices.push(args[2]);}},
  window:{addEventListener(type,fn){events[type]=fn;}},
  BroadcastChannel:class { addEventListener(_,fn){events.channel=fn;} postMessage(value){notices.push(value);} close(){notices.push('closed');} },
  fetch:async(url,options)=>{
    requests.push({url,...options}); let result;
    if(url.endsWith('/bootstrap'))result=bootstrapError || {csrf:'session-bound-csrf'};
    else if(url.endsWith('/me'))result=state ? {state} : {error:{code:'account_auth_required'},status:401};
    else result=reply ? await reply(url,options) : {state:'ready'};
    return {ok:!result.error,status:result.status||200,json:async()=>result};
  }};
  vm.runInNewContext(source,ctx);
  return {nodes,requests,notices,events,navigation,reply(fn){reply=fn;},submit(id){nodes.get(id).listeners.submit({preventDefault(){}});}};
}

test('initial sign-in clears URL fragments without sending provider tokens',async()=>{
  const h=harness({hash:'#access_token=never-submit-this'});await tick();
  assert.equal(h.nodes.get('login-form').hidden,false);
  assert.deepEqual(h.notices,['/auth/sign-in']);
  assert.equal(h.requests.some(r=>JSON.stringify(r).includes('never-submit-this')),false);
  assert.match(h.nodes.get('account-status').textContent,/copy the original email link/);
});
test('gate denial exposes only the access-code form',async()=>{
  const h=harness({bootstrapError:{error:{code:'staging_access_required'},status:401}});await tick();
  assert.equal(h.nodes.get('gate-form').hidden,false);assert.equal(h.nodes.get('login-form').hidden,true);
});
test('login blocks double submission, sends CSRF and clears secrets',async()=>{
  const h=harness();await tick();let release;
  h.nodes.get('login-email').value='test@example.test';h.nodes.get('login-password').value='offline-password';
  h.reply(()=>new Promise(resolve=>{release=resolve;}));h.submit('login-form');h.submit('login-form');await tick();
  assert.equal(h.requests.filter(r=>r.url.endsWith('/login')).length,1);
  assert.equal(h.requests.at(-1).headers['X-CSRF-Token'],'session-bound-csrf');
  assert.equal(h.nodes.get('login-form')['aria-busy'],'true');
  release({state:'ready'});await tick();assert.equal(h.nodes.get('account-ready').hidden,false);
  assert.equal(h.nodes.get('login-password').value,'');assert.equal(h.notices.includes('changed'),true);
});
test('invitation sends a link explicitly and stops at password setup',async()=>{
  const h=harness({pathname:'/auth/callback'});await tick();
  assert.equal(h.nodes.get('link-form').hidden,false);
  h.nodes.get('link-email').value='test@example.test';h.nodes.get('email-link').value='private-one-time-link';
  h.reply(()=>({state:'activation'}));h.submit('link-form');await tick();
  assert.equal(h.nodes.get('password-form').hidden,false);assert.equal(h.nodes.get('email-link').value,'');
  const request=h.requests.find(r=>r.url.endsWith('/accept'));
  assert.deepEqual(JSON.parse(request.body),{email:'test@example.test',link:'private-one-time-link'});
  assert.equal(h.requests.some(r=>r.url.includes('/password')),false);
});
test('recovery has generic confirmation and explicit reset selection',async()=>{
  const h=harness();await tick();h.navigation[2].listeners.click();
  h.nodes.get('recovery-email').value='test@example.test';h.reply(()=>({message:'If eligible, check your inbox.'}));
  h.submit('recovery-form');await tick();assert.match(h.nodes.get('account-status').textContent,/If eligible/);
  h.navigation[3].listeners.click();assert.match(h.nodes.get('link-instructions').textContent,/Reset password/);
});
test('password mismatch never calls provider and all passwords clear',async()=>{
  const h=harness({state:'recovery'});await tick();h.nodes.get('new-password').value='offline-password';h.nodes.get('confirm-password').value='different';
  h.submit('password-form');await tick();assert.match(h.nodes.get('account-error').textContent,/must match/);
  assert.equal(h.requests.some(r=>r.url.endsWith('/password')),false);assert.equal(h.nodes.get('new-password').value,'');
});
test('expired account action returns to sign-in without displaying history',async()=>{
  const h=harness({state:'ready'});await tick();h.reply(()=>({error:{message:'expired'},status:401}));
  h.nodes.get('logout').listeners.click();await tick();assert.equal(h.nodes.get('account-ready').hidden,true);
  assert.equal(h.nodes.get('login-form').hidden,false);assert.match(h.nodes.get('account-status').textContent,/expired/);
});
test('network failure re-enables buttons and leaves a usable alert',async()=>{
  const h=harness();await tick();h.reply(()=>{throw new TypeError('Connection interrupted.');});
  h.submit('login-form');await tick();assert.equal(h.nodes.get('account-error').hidden,false);
  assert.equal(h.nodes.get('logout').disabled,false);
});
test('page lifecycle clears secrets and refreshes restored or changed account UI',async()=>{
  const h=harness();await tick();h.nodes.get('login-password').value='private';
  h.events.pagehide();assert.equal(h.nodes.get('login-password').value,'');
  h.events.pageshow({persisted:true});h.events.channel();assert.equal(h.notices.filter(n=>n==='reload').length,2);
});
