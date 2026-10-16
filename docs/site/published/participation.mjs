import {enhanceCommands} from './command-copy.mjs?v=20261016-public1';

const steps=['installation','preparation','running','results'];
export function participantState(raw={}) {
  raw=raw&&typeof raw==='object'?raw:{};
  return {step:Number.isInteger(raw.step)&&raw.step>=0&&raw.step<4?raw.step:0,
    shell:raw.shell==='powershell'?'powershell':'posix'};
}
export function participantAction(input,action) {
  const state=participantState(input);
  if(action.type==='next')state.step=Math.min(3,state.step+1);
  if(action.type==='back')state.step=Math.max(0,state.step-1);
  if(action.type==='select'&&Number.isInteger(action.index)&&action.index>=0&&action.index<4)state.step=action.index;
  if(action.type==='shell'&&['posix','powershell'].includes(action.value))state.shell=action.value;
  return state;
}
export function stepFromHash(hash) {
  let id;try{id=decodeURIComponent(hash.replace(/^#/,''));}catch{return null;}
  const index=steps.indexOf(id);return index<0?null:index;
}
export function openParticipantResource(root,hash) {
  let id;try{id=decodeURIComponent(hash.replace(/^#/,''));}catch{return null;}
  const detail=[...root.querySelectorAll('.participant-resource')].find(node=>node.id===id);
  if(!detail)return null;
  detail.open=true;
  let parent=detail.parentElement?.closest('details');
  while(parent){parent.open=true;parent=parent.parentElement?.closest('details');}
  return detail;
}

function mount(root) {
  const storageKey='async-rbench-participant-checklist-v1';
  let state=participantState();
  try{state=participantState(JSON.parse(sessionStorage.getItem(storageKey)));}catch{}
  const initial=stepFromHash(location.hash);if(initial!==null)state.step=initial;
  const tabs=[...root.querySelectorAll('[data-participant-step]')];
  const panels=[...root.querySelectorAll('[data-participant-panel]')];
  const next=root.querySelector('[data-participant-next]'),back=root.querySelector('[data-participant-back]');
  const status=root.querySelector('.participant-status');
  const tr=(zh,en)=>document.documentElement.lang==='zh'?zh:en;
  root.querySelector('.participant-steps').setAttribute('role','tablist');
  for(const[ i,tab]of tabs.entries()){tab.setAttribute('role','tab');panels[i].setAttribute('role','tabpanel');panels[i].setAttribute('aria-labelledby',tab.id);}
  function render(){
    tabs.forEach((tab,i)=>{tab.setAttribute('aria-selected',String(i===state.step));tab.tabIndex=i===state.step?0:-1;});
    panels.forEach((panel,i)=>{panel.hidden=i!==state.step;});
    for(const button of root.querySelectorAll('[data-shell]'))button.setAttribute('aria-pressed',String(button.dataset.shell===state.shell));
    for(const terminal of root.querySelectorAll('[data-participant-shell]'))terminal.hidden=terminal.dataset.participantShell!==state.shell;
    back.disabled=state.step===0;
    next.textContent=state.step===3?tr('评测 200 个任务 ↗','Evaluate 200 tasks ↗'):tr('下一步 →','Continue →');
    try{sessionStorage.setItem(storageKey,JSON.stringify(state));}catch{}
  }
  function select(index,{focus=false,scroll=false}={}){
    state=participantAction(state,{type:'select',index});render();
    const url=new URL(location.href);url.hash=steps[state.step];history.replaceState(null,'',url);
    if(scroll)root.querySelector('.participant-steps').scrollIntoView({block:'start',behavior:'instant'});
    if(focus)panels[state.step].querySelector('h3').focus({preventScroll:true});
  }
  tabs.forEach((tab,i)=>{
    tab.addEventListener('click',event=>{if(event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;event.preventDefault();select(i);});
    tab.addEventListener('keydown',event=>{
      const index=event.key==='ArrowRight'?(i+1)%4:event.key==='ArrowLeft'?(i+3)%4:event.key==='Home'?0:event.key==='End'?3:null;
      if(index===null)return;event.preventDefault();select(index);tabs[index].focus({preventScroll:true});
    });
  });
  for(const button of root.querySelectorAll('[data-shell]'))button.addEventListener('click',()=>{state=participantAction(state,{type:'shell',value:button.dataset.shell});render();});
  back.addEventListener('click',()=>select(state.step-1,{focus:true,scroll:true}));
  next.addEventListener('click',()=>{if(state.step<3)select(state.step+1,{focus:true,scroll:true});else{const target=openParticipantResource(root,'#scale');location.hash='scale';target?.scrollIntoView({block:'start'});}});
  function hashChanged(){const index=stepFromHash(location.hash);if(index!==null){state=participantAction(state,{type:'select',index});render();}openParticipantResource(root,location.hash);}
  addEventListener('hashchange',hashChanged);addEventListener('popstate',hashChanged);
  document.addEventListener('site-language-change',()=>render());
  enhanceCommands(root);root.classList.add('participant-enhanced');render();
  const resource=openParticipantResource(root,location.hash);
  resource?.scrollIntoView({block:'start',behavior:'instant'});
}

if(typeof document!=='undefined'){
  const start=()=>document.querySelectorAll('[data-participation]').forEach(mount);
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',start,{once:true});else start();
}
