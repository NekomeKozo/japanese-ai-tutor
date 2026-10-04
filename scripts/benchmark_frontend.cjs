// Reuse the real frontend regression harness, without registering its tests.
// Local VM measures request counts, not browser paint or Core Web Vitals.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm');
const tests=path.join(__dirname,'..','tests');
const source=fs.readFileSync(path.join(tests,'frontend.test.cjs'),'utf8');
const make=vm.runInNewContext(source.slice(0,source.indexOf('\ntest('))+'\nharness', {require,__dirname:tests,console,Event,AbortController,Blob,URLSearchParams,Intl,setTimeout,clearTimeout});
(async()=>{
  const h=make();let calls=0,resolvers=[];
  h.ctx.fetch=()=>{calls++;return new Promise(resolve=>resolvers.push(()=>resolve({ok:true,json:async()=>({learner_id:'learner'})})));};
  const result=h.run("Promise.all([api('/api/learners/learner/profile'),api('/api/learners/learner/profile'),api('/api/learners/learner/profile')])");
  const overlapping=calls;for(const resolve of resolvers)resolve();await result;
  const before=calls;
  h.run("flashcards.start('vocabulary'); for(let i=0;i<50;i++){flashcards.restart();renderFlashcard();flashcards.reveal();renderFlashcard();flashcards.move(1);renderFlashcard();}");
  const data={environment:'Node VM, real frontend scripts, mocked fetch and DOM',overlapping_identical_get_requests:overlapping,free_practice_50_cycles_network_requests:calls-before};
  fs.writeFileSync(process.argv[2],JSON.stringify(data,null,2)+'\n');console.log(JSON.stringify(data));
})().catch(error=>{console.error(error);process.exitCode=1;});
