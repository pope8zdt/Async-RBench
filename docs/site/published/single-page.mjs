import {pageWindow,activeSection,sameFilters,initialAnchor} from './research-logic.mjs?v=20261016-public1';
import {filterTasks} from './assets/logic.mjs';
import {enhanceCommands} from './command-copy.mjs?v=20261016-public1';
import {enhanceFigures} from './figure-viewer.mjs?v=20261016-public1';

const english=()=>document.documentElement.lang==='en';
const tr=(zh,en)=>english()?en:zh;
const el=(tag,cls,text)=>{const node=document.createElement(tag);if(cls)node.className=cls;if(text!==undefined)node.textContent=text;return node;};
const openingHash=location.hash;
let openingInterrupted=false;
for(const event of ['pointerdown','keydown','wheel','touchstart'])addEventListener(event,()=>{openingInterrupted=true;},{once:true,passive:true});

function restoreOpeningPosition(){
  requestAnimationFrame(()=>requestAnimationFrame(()=>{
    const id=initialAnchor(openingHash,location.hash,openingInterrupted,location.search);
    const target=id&&(document.getElementById(id)||document.getElementById(initialAnchor(openingHash,location.hash,openingInterrupted)));
    if(!target)return;
    for(let p=target;p;p=p.parentElement)if(p.tagName==='DETAILS')p.open=true;
    target.scrollIntoView({block:'start',behavior:'instant'});
  }));
}

function navigation(){
  const sections=[...document.querySelectorAll('#top,.research-chapter')];
  const links=[...document.querySelectorAll('.research-nav a')];
  let frame;
  function update(){
    frame=undefined;
    const active=activeSection(sections.map(s=>({id:s.id,top:s.getBoundingClientRect().top})),document.querySelector('.site-header')?.offsetHeight||80);
    for(const link of links){
      if(link.hash==='#'+active)link.setAttribute('aria-current','location');
      else link.removeAttribute('aria-current');
    }
  }
  addEventListener('scroll',()=>{if(!frame)frame=requestAnimationFrame(update);},{passive:true});
  addEventListener('resize',update);
  document.addEventListener('site-language-change',()=>requestAnimationFrame(update));
  update();
}

function catalog(){
  const host=document.getElementById('task-rows'),dataNode=document.getElementById('site-data');
  if(!host||!dataNode)return;
  const data=JSON.parse(dataNode.textContent);
  const rows=new Map([...host.children].map(row=>[row.dataset.task,row]));
  const query=document.getElementById('task-search'),source=document.getElementById('task-source'),difficulty=document.getElementById('task-difficulty');
  const count=document.getElementById('task-count');
  const pager=el('nav','catalog-pager');pager.setAttribute('aria-label','Task pages');
  const previous=el('button','pager-button'),next=el('button','pager-button'),position=el('span','pager-position');
  const label=el('label','page-picker'),select=el('select'),labelText=el('span','sr-only');
  const announcement=el('span','sr-only');announcement.setAttribute('aria-live','polite');announcement.setAttribute('aria-atomic','true');
  previous.type=next.type='button';label.append(labelText,select);pager.append(previous,position,label,next,announcement);host.after(pager);
  host.classList.add('is-paginated');
  let page=1,priorFilters=null,matched=[];
  const choices=[];
  for(const term of document.querySelectorAll('#tasks .source-strip dt')) {
    const name=term.textContent.trim(),option=[...source.options].find(o=>o.textContent.trim()===name);
    if(!option)continue;
    const button=el('button','source-choice',name);button.type='button';button.dataset.source=option.value;button.setAttribute('aria-controls','task-rows');
    button.addEventListener('click',()=>{source.value=source.value===option.value?'':option.value;source.dispatchEvent(new Event('change',{bubbles:true}));});
    term.replaceChildren(button);choices.push(button);
  }
  function render(){
    const filters={query:query.value,source:source.value,difficulty:difficulty.value};
    if(!sameFilters(priorFilters,filters))page=1;
    priorFilters=filters;
    matched=filterTasks(data.tasks,filters);
    const range=pageWindow(matched.length,page,6);page=range.page;
    const visible=new Set(matched.slice(range.start,range.end).map(task=>task.id));
    for(const[id,row]of rows)row.hidden=!visible.has(id);
    previous.textContent=tr('← 上一页','← Previous');next.textContent=tr('下一页 →','Next →');
    previous.disabled=page===1;next.disabled=page===range.pages;
    previous.hidden=next.hidden=label.hidden=matched.length<=6;
    position.textContent=matched.length?`${range.start+1}–${range.end} / ${matched.length}`:tr('无匹配任务','No matching tasks');
    labelText.textContent=tr('选择页码','Choose page');
    select.replaceChildren();
    for(let p=1;p<=range.pages;p++){const o=el('option','',tr(`第 ${p} / ${range.pages} 页`,`Page ${p} of ${range.pages}`));o.value=p;select.append(o);}
    select.value=page;
    announcement.textContent=tr(`找到 ${matched.length} 个任务，当前显示 ${matched.length?range.start+1:0} 至 ${range.end}。`,`${matched.length} tasks found. Showing ${matched.length?range.start+1:0} through ${range.end}.`);
    for(const button of choices)button.setAttribute('aria-pressed',String(source.value===button.dataset.source));
  }
  function turn(value){page=value;render();document.querySelector('#tasks .catalog')?.scrollIntoView({block:'start'});}
  previous.addEventListener('click',()=>turn(page-1));next.addEventListener('click',()=>turn(page+1));select.addEventListener('change',()=>turn(Number(select.value)));
  // The original filter owns task-count; our pagination never writes it.
  // Watching that signal avoids observing our own hidden-row mutations.
  new MutationObserver(render).observe(count,{childList:true,characterData:true,subtree:true});
  document.addEventListener('site-language-change',render);
  render();
}

function mount(){navigation();catalog();enhanceCommands(document.getElementById('guide'));enhanceFigures(document.querySelector('main'));document.documentElement.classList.add('research-ready');restoreOpeningPosition();document.addEventListener('evidence-ready',restoreOpeningPosition,{once:true});}
if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',mount,{once:true});else mount();
