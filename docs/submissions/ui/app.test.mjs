import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {setImmediate} from 'node:timers/promises';
import test from 'node:test';

const code = await readFile(new URL('./app.mjs', import.meta.url), 'utf8');
const AsyncFunction = Object.getPrototypeOf(async function(){}).constructor;
const settle = async () => { await setImmediate(); };
const deferred = () => {let resolve,reject; const promise=new Promise((r,j)=>{resolve=r;reject=j;}); return {promise,resolve,reject};};
const row = {
  id:'a',owner:'participant',status:'pending',revision:1,version:1,hash:'hash',history:[],
  validation:{metrics:{episodes:200,drs:64.8,success:75}},
  bundle:{metadata:{agent:'Private package A',model:'Synthetic',organization:'Lab',code_revision:'revision'},
    evidence:[{episode_id:'demo-1',sha256:'hash',content:{events:[{kind:'task_started'}]}}]},
};

// Only DOM and transport boundaries are doubled. The actual controller runs its
// startup and registered event handlers, with response order controlled here.
async function controller(overrides={}) {
  const app={innerHTML:'',setAttribute(){},scrollIntoView(){}};
  const identity={value:'participant'},message={textContent:'',className:''};
  const handlers={},requests=[];
  const root={
    querySelector:s=>({'#submission-app':app,'#submission-identity':identity,'#submission-message':message,'#event-visual':{innerHTML:''}}[s]||null),
    querySelectorAll:()=>[],contains:button=>!button.outside,
    addEventListener:(kind,handler)=>{handlers[kind]=handler;},
  };
  const document={querySelector:()=>root,documentElement:{lang:'en'}};
  const fetch=async(path,options)=>{
    requests.push(path);
    const json=async()=>{
      if(overrides[path])return overrides[path](options);
      if(path==='/api/session')return {role:options.method==='POST'?JSON.parse(options.body).role:'participant',csrf:'token'};
      if(path==='/api/submissions')return {items:[]};
      throw new Error(`Unexpected request: ${path}`);
    };
    return {ok:true,json};
  };
  await new AsyncFunction('document','fetch','matchMedia',code)(document,fetch,()=>({matches:true}));
  return {app,message,requests,async click(dataset={},id='',outside=false){
    const button={dataset,id,disabled:false,outside};
    handlers.click({target:{closest:()=>button}}); await settle(); return button;
  },async identity(value){identity.value=value;handlers.change({target:identity});await settle();},
  async upload(file,id='file'){handlers.change({target:{id,files:[file]}});await settle();}};
}

test('late detail response cannot reveal the previous identity package',async()=>{
  const detail=deferred();
  const ui=await controller({'/api/submissions/a':()=>detail.promise});
  await ui.click({open:'a'});
  await ui.identity('other-participant');
  detail.resolve(row);await settle();
  assert.doesNotMatch(ui.app.innerHTML,/Private package A/);
  assert.match(ui.app.innerHTML,/Your submissions/);
});

test('late validation cannot restore a package after identity changes',async()=>{
  const validation=deferred();
  const ui=await controller({'/api/demo-package':()=>row.bundle,'/api/validate':()=>validation.promise});
  await ui.click({},'sample');
  await ui.identity('other-participant');
  validation.resolve({valid:true,metrics:{episodes:200,drs:64.8,success:75}});await settle();
  assert.doesNotMatch(ui.app.innerHTML,/Submit for review/);
  assert.equal(ui.message.textContent,'');
});

test('late list response cannot replace the next identity submission list',async()=>{
  const list=deferred();let calls=0;
  const ui=await controller({'/api/submissions':()=>++calls===2?list.promise:{items:[]}});
  await ui.click({view:'review'});
  await ui.identity('other-participant');
  list.resolve({items:[{...row,metadata:row.bundle.metadata}]});await settle();
  assert.doesNotMatch(ui.app.innerHTML,/Private package A/);
});

test('buttons outside the submission section are not handled or disabled',async()=>{
  const ui=await controller();
  const before=ui.requests.length;
  const button=await ui.click({view:'community'},'theme',true);
  assert.equal(ui.requests.length,before);
  assert.equal(button.disabled,false);
});

test('slow file read cannot submit previous identity data for a new identity',async()=>{
  const file=deferred();
  const ui=await controller({'/api/validate':()=>({valid:true,metrics:{episodes:200,drs:64.8,success:75}})});
  await ui.upload({size:100,text:()=>file.promise});
  await ui.identity('other-participant');
  file.resolve(JSON.stringify(row.bundle));await settle();
  assert.doesNotMatch(ui.app.innerHTML,/Private package A/);
  assert.equal(ui.requests.includes('/api/validate'),false);
});

test('failed file read from a previous identity does not overwrite current feedback',async()=>{
  const file=deferred();
  const ui=await controller();
  await ui.upload({size:100,text:()=>file.promise});
  await ui.identity('other-participant');
  file.reject(new Error('Previous private upload error'));await settle();
  assert.equal(ui.message.textContent,'');
});
