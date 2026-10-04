const test=require('node:test'),assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const version='a'.repeat(20),origin='https://goigrow.test';
const offline='/offline?v='+version;
const urls=[offline,'/static/pwa/offline.css?v='+version,'/static/pwa/icon-192.png?v='+version];
function worker(options={}) {
  const events={},stores=new Map(),deleted=[],requests=[];
  const key=request=>typeof request==='string'?request:request.url;
  const caches={async open(name){if(!stores.has(name))stores.set(name,new Map());const store=stores.get(name);return {async put(request,response){store.set(key(request),response.clone());},async match(request){return store.get(key(request))?.clone();}};},async keys(){return [...stores.keys()];},async delete(name){deleted.push(name);return stores.delete(name);}};
  const context=vm.createContext({URL,Request,Response,Set,Error,caches,self:{location:{origin},addEventListener:(name,fn)=>events[name]=fn},fetch:async request=>{requests.push(request);return options.fetch?options.fetch(request):new Response('public only');}});
  const config={version,offline,assets:urls.map(url=>({url,integrity:'sha256-test'}))};
  vm.runInContext(fs.readFileSync(path.join(__dirname,'../frontend/service-worker.js'),'utf8').replace('__PWA_CONFIG__',JSON.stringify(config)),context);
  const lifetime=async type=>{let done;events[type]({waitUntil:promise=>done=promise});await done;};
  function request(url,opts={}) { let response;events.fetch({request:{url:new URL(url,origin).href,method:opts.method||'GET',mode:opts.mode||'cors',headers:new Headers(opts.headers)},respondWith:p=>response=p});return response;}
  return {events,stores,deleted,requests,lifetime,request};
}
test('install caches only three pinned anonymous public assets',async()=>{
  const h=worker();await h.lifetime('install');assert.equal(h.requests.length,3);
  for(const request of h.requests){assert.equal(request.credentials,'omit');assert.equal(request.redirect,'error');assert.equal(request.cache,'reload');assert.equal(request.integrity,'sha256-test');}
  assert.deepEqual([...h.stores.values()][0].size,3);
  const before=h.requests.length;assert.equal(await (await h.request(urls[1])).text(),'public only');assert.equal(h.requests.length,before);
});
test('fail closed on cookie, redirect, error or opaque precache responses',async()=>{
  for(const response of [new Response('x',{headers:{'Set-Cookie':'test=only'}}),new Response('x',{status:401}),{ok:true,status:200,redirected:true,type:'basic',headers:new Headers()},{ok:true,status:200,redirected:false,type:'opaque',headers:new Headers()}]) {
    const h=worker({fetch:async()=>response});await assert.rejects(h.lifetime('install'));assert.equal(h.stores.size,0);
  }
});
test('activation cleans only obsolete caches owned by this app',async()=>{
  const h=worker();await h.lifetime('install');const old='goigrow-public-v1-'+ 'b'.repeat(20);
  h.stores.set(old,new Map());h.stores.set('another-app',new Map());h.stores.set('goigrow-public-v1-not-an-owned-version',new Map());
  await h.lifetime('activate');assert.deepEqual(h.deleted,[old]);assert.ok(h.stores.has('goigrow-public-v1-'+version));assert.ok(h.stores.has('another-app'));
});
test('API, protected assets, private content, mutations and wrong versions bypass the worker',()=>{
  const h=worker();for(const url of ['/api/learners/a/profile','/api/learners/a/reviews/due','/api/chat','/api/access','/static/app.js','/static/flashcard-catalog.json','/reference/book.pdf','/static/pwa/offline.css','/static/pwa/offline.css?v=old','https://other.test/'+urls[1]])assert.equal(h.request(url),undefined,url);
  assert.equal(h.request('/',{method:'POST',mode:'navigate'}),undefined);
  assert.equal(h.request(urls[1],{headers:{Authorization:'test-only'}}),undefined);
  assert.equal(h.request(urls[1],{headers:{Range:'bytes=0-9'}}),undefined);
  assert.equal(h.stores.size,0);
});
test('navigation asks the server and preserves authentication/error responses',async()=>{
  for(const status of [200,401,403,503]) {
    const h=worker({fetch:async()=>new Response('server response',{status})});const response=await h.request('/',{mode:'navigate'});
    assert.equal(response.status,status);assert.equal(await response.text(),'server response');assert.equal(h.stores.size,0);
  }
});
test('offline root/access navigation gets generic 503; reconnect returns the server',async()=>{
  let online=true;const h=worker({fetch:async()=>{if(!online)throw new TypeError('offline');return new Response('generic public offline message');}});
  await h.lifetime('install');online=false;
  for(const url of ['/','/access']){const response=await h.request(url,{mode:'navigate'});assert.equal(response.status,503);assert.equal(await response.text(),'generic public offline message');}
  assert.equal(h.request('/api/chat',{method:'POST'}),undefined);
  online=true;assert.equal((await h.request('/',{mode:'navigate'})).status,200);
});
test('missing cache offers a generic offline error and never writes runtime responses',async()=>{
  const h=worker({fetch:async()=>{throw new TypeError('offline');}});const response=await h.request('/',{mode:'navigate'});
  assert.equal(response.status,503);assert.match(await response.text(),/needs an internet connection/);assert.equal([...h.stores.values()][0].size,0);
  const runtime=worker();await runtime.request(urls[1]);assert.equal([...runtime.stores.values()][0].size,0);
});
test('worker has no immediate activation, client reload, sync or message command',()=>{
  const h=worker();assert.deepEqual(Object.keys(h.events),['install','activate','fetch']);
  const source=fs.readFileSync(path.join(__dirname,'../frontend/service-worker.js'),'utf8');
  assert.doesNotMatch(source,/self\.skipWaiting\s*\(|clients\.claim\s*\(|\.navigate\s*\(|indexedDB|localStorage/);
});
