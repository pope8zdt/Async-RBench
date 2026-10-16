import {formatTime} from './flow-model.mjs';
import {recordExcerpt} from './trajectory-logic.mjs';
import {defaultEvents,keyEvents,readEvidenceLocation,evidenceLocation} from './evidence-state.mjs?v=20261016-public1';
import {eventLabel} from './evidence-labels.mjs?v=20261016-public1';
import {loadArchive} from './evidence-loader.mjs?v=20261016-public1';

const zh=()=>document.documentElement.lang!=='en';
const tr=(a,b)=>zh()?a:b;
const txt=v=>v[zh()?'zh':'en'];
const node=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
const vector=(tag,attrs={},text)=>{const n=document.createElementNS('http://www.w3.org/2000/svg',tag);for(const[k,v]of Object.entries(attrs))n.setAttribute(k,v);if(text!==undefined)n.textContent=text;return n;};
const titles={release:['旧验证遇到新版本','Old tests, new revision'],replay:['同一个结果被交付两次','One result, two deliveries'],'early-stop':['文件已收到，任务未完成','Files received. Task unfinished.'],reconsider:['从拒绝，到采纳','From reject to use'],defer:['先暂缓，再采纳','Defer now, use later'],continue:['一个中断，另一个返回','One stops. Another returns.']};
const models={release:['GPT-5.6 Terra','openai.svg'],replay:['Claude Sonnet 5','claude-color.svg'],'early-stop':['Qwen3.5 27B','qwen-color.svg'],reconsider:['Claude Sonnet 5','claude-color.svg'],defer:['Claude Sonnet 5','claude-color.svg'],continue:['Claude Sonnet 5','claude-color.svg']};
const names={release:['版本变化','Revision'],replay:['重复交付','Replay'],'early-stop':['产物缺口','Artifacts'],reconsider:['重新采纳','Reconsider'],defer:['延后处理','Defer'],continue:['继续执行','Continue']};

export function recordPreview(event){
  const full=recordExcerpt(event).text;
  const lines=full.split('\n').filter(line=>line.trim());
  let text=lines.slice(0,3).join('\n');
  const truncated=lines.length>3||text.length>360;
  if(truncated)text=text.slice(0,359).trimEnd()+'…';
  return {text,truncated};
}

export function caseFacts(c) {
  const event=seq=>c.events.find(e=>e.seq===seq);
  if(c.id==='release')return {before:event(165).record.evidence,after:event(195).record.evidence,compare:event(289),failed:event(303),retest:event(315),exit:event(316)};
  if(c.id==='replay')return {completion:event(292).record.completion_id,origin:event(722).record.replay_of_occurrence_id,replay:event(722).record.delivery_occurrence_id,events:[292,317,432,720,722,754,800].map(event)};
  return {transfers:c.events.filter(e=>e.type==='child_path_promotion_result'&&e.record.success===true),failure:event(265),cancel:event(428),end:event(430),children:c.lanes.filter(l=>l.id.startsWith('child'))};
}

export function compactEvidence(c){
  const facts=caseFacts(c);
  if(c.id==='release')return {heads:['main','dev'].map(branch=>({branch,before:facts.before[`tested_${branch}_head`],after:facts.after[`${branch}_head`]})),sequence:[facts.compare,facts.failed,facts.retest,facts.exit]};
  if(c.id==='replay')return {completion:facts.completion,events:facts.events};
  return {files:facts.transfers,missingPlan:!facts.transfers.some(e=>e.record.destination_path.endsWith('/plan_b2.jsonl')),cancel:facts.cancel,end:facts.end};
}

export function focusEvidence(c){
  const extra={
    reconsider:[[305,'Result delivered','completion_id'],[382,'First decision','decision'],[684,'Later decision','decision']],
    defer:[[146,'Result presented','completion_id'],[150,'First decision','decision'],[316,'Later decision','decision']],
    continue:[[387,'Cancelled by infrastructure','child_id'],[476,'Another child returns','child_id'],[505,'Result accepted','decision']]
  }[c.id];
  if(extra)return extra.map(([seq,label,key])=>({seq,label,value:c.events.find(e=>e.seq===seq).record[key]}));
  const f=caseFacts(c);
  if(c.id==='release')return [
    {seq:165,label:'Tested revision',value:f.before.tested_main_head.slice(0,7)},
    {seq:195,label:'Current revision',value:f.after.main_head.slice(0,7)},
    {seq:289,label:'Compare',value:'bottle.py'}
  ];
  if(c.id==='replay')return [
    {seq:317,label:'First shown',value:c.events.find(e=>e.seq===317).record.delivery_occurrence_id},
    {seq:722,label:'Replay',value:f.completion},
    {seq:754,label:'Shown again',value:c.events.find(e=>e.seq===754).record.delivery_occurrence_id}
  ];
  return f.transfers.map((e,i)=>({seq:e.seq,label:i?'Report received':'Plan received',value:e.record.destination_path.split('/').pop()})).concat({seq:f.end.seq,label:'Episode ended',value:f.end.record.local_status});
}

function observedSequence(c,select){
  const timeline=node('ol','evidence-sequence');timeline.lang='en';
  for(const point of focusEvidence(c)){
    const event=c.events.find(e=>e.seq===point.seq),row=node('li'),button=node('button','sequence-event');
    button.type='button';button.dataset.seq=point.seq;button.classList.add('figure-source');
    button.setAttribute('aria-label',`Inspect event ${point.seq}`);
    button.append(node('span','sequence-time',formatTime(event.elapsed_ms)),node('span','sequence-label',point.label),node('strong','sequence-value',point.value),node('span','sequence-id',`#${point.seq}`));
    button.addEventListener('click',()=>select(point.seq));row.append(button);timeline.append(row);
  }
  return timeline;
}

function figure(title){
  const s=vector('svg',{viewBox:'0 0 780 460',role:'group','aria-label':title,class:'evidence-figure',lang:'en'});
  s.append(vector('title',{},title));return s;
}
function text(s,x,y,content,cls='fig-text',extra={}){s.append(vector('text',{x,y,class:cls,...extra},content));}
function rect(s,x,y,w,h,cls='fig-paper'){s.append(vector('rect',{x,y,width:w,height:h,rx:3,class:cls}));}
function line(s,x1,y1,x2,y2,cls='fig-line'){s.append(vector('line',{x1,y1,x2,y2,class:cls}));}
function path(s,d,cls='fig-line'){s.append(vector('path',{d,class:cls}));}
function source(s,seq,x,y,select){
  const g=vector('g',{role:'button',tabindex:0,'aria-label':`Inspect event ${seq}`,class:'figure-source','data-seq':seq});
  g.append(vector('rect',{x:x-7,y:y-24,width:56,height:40,rx:3,fill:'transparent'}),vector('text',{x,y,class:'fig-source'},`#${seq}`));
  g.addEventListener('click',()=>select(seq));g.addEventListener('keydown',e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();select(seq);}});s.append(g);
}

function revision(c,select){
  const tr=(_zh,en)=>en;
  const f=caseFacts(c),s=figure(tr('测试报告与新仓库版本对照','Tested revisions compared with the new repository heads'));
  text(s,24,27,tr('同一仓库，两组版本','One repository, two revision pairs'),'fig-heading');
  rect(s,24,48,310,180,'fig-green');rect(s,446,48,310,180,'fig-blue');
  text(s,43,77,tr('补丁测试报告','Patch test report'),'fig-label');source(s,165,277,77,select);
  text(s,465,77,tr('仓库清理结果','Repository cleanup'),'fig-label');source(s,195,699,77,select);
  for(const[branch,y]of [['main',122],['dev',177]]){
    text(s,43,y,branch,'fig-mono');text(s,43,y+23,f.before[`tested_${branch}_head`].slice(0,12),'fig-hash');
    text(s,465,y,branch,'fig-mono');text(s,465,y+23,f.after[`${branch}_head`].slice(0,12),'fig-hash');
    line(s,345,y+10,433,y+10);path(s,`M426 ${y+5} L434 ${y+10} L426 ${y+15}`);text(s,389,y-4,tr('变化','changed'),'fig-small',{'text-anchor':'middle'});
  }
  text(s,24,256,tr('报告验证的是旧快照；新的 head 需要重新检查。','The report tests older snapshots; the new heads need another check.'),'fig-text');
  rect(s,24,279,732,68,'fig-code');text(s,43,303,tr('主代理实际执行的版本比较（命令摘录）','Revision comparison executed by the main agent (excerpt)'),'fig-small');source(s,289,699,303,select);
  text(s,43,329,'git diff f2ff20b..4f8b595 -- bottle.py','fig-mono');
  line(s,48,395,728,395);[48,385,728].forEach(x=>s.append(vector('circle',{cx:x,cy:395,r:5,class:x===48?'fig-dot fig-failed':'fig-dot'})));
  text(s,24,380,tr('修复命令 (exit 128)','Repair command (exit 128)'),'fig-small');source(s,303,24,425,select);
  text(s,292,380,'validation_test.py','fig-small');source(s,315,365,425,select);
  text(s,622,380,tr('重试命令 (exit 0)','Retry (exit 0)'),'fig-small');source(s,316,709,425,select);
  return s;
}

function repeated(c,select){
  const tr=(_zh,en)=>en;
  const f=caseFacts(c),s=figure(tr('同一个完成结果的两次交付与主代理确认','Two deliveries of one completion and the main-agent acknowledgments'));
  text(s,24,27,'completion-2','fig-heading');text(s,215,27,tr('一个完成结果，不是两个子任务','One completion, not two children'),'fig-text');
  const columns=[190,414,641];
  [tr('子任务 child-4','Child child-4'),tr('交付记录','Delivery record'),tr('主代理','Main agent')].forEach((v,i)=>{text(s,columns[i],64,v,'fig-label',{'text-anchor':'middle'});line(s,columns[i],81,columns[i],421,'fig-lifeline');});
  const rows=[
    [292,109,190,414,tr('首次到达','First arrival'),'gateway-occ-2'],
    [317,157,414,641,tr('首次呈现','First presentation'),'occ-2'],
    [432,205,641,414,'reject',''],
    [720,253,641,414,'use',tr('重放之前','before replay')],
    [722,301,414,414,tr('同一结果重放','Same result replayed'),'gateway-occ-5'],
    [754,349,414,641,tr('第二次呈现','Second presentation'),'occ-5'],
    [800,397,641,414,'use',tr('再次确认','acknowledged again')]
  ];
  rect(s,369,277,382,35,'fig-pink');
  rows.forEach(([seq,y,a,b,label,detail])=>{
    const e=c.events.find(e=>e.seq===seq);text(s,24,y-2,formatTime(e.elapsed_ms),'fig-time');source(s,seq,101,y-2,select);
    if(a!==b){line(s,a,y,b,y);const d=b>a?-1:1;path(s,`M${b+d*7} ${y-4}L${b} ${y}L${b+d*7} ${y+4}`);}
    else s.append(vector('circle',{cx:a,cy:y,r:5,class:'fig-dot'}));
    text(s,a===b?433:Math.min(a,b)+12,y-8,label,'fig-small');
    if(detail)text(s,a===b?580:Math.min(a,b)+12,y+18,detail,'fig-tiny');
  });
  text(s,24,449,tr('重放关联原交付 gateway-occ-2；use 的改变发生在重放之前。','Replay links back to gateway-occ-2; the change to use precedes replay.'),'fig-small');
  return s;
}

function artifacts(c,select){
  const tr=(_zh,en)=>en;
  const f=caseFacts(c),s=figure(tr('任务结束时的文件交付与子任务状态','File transfers and child states at the episode endpoint'));
  text(s,24,27,tr('主工作区收到什么？','What reached the main workspace?'),'fig-heading');
  rect(s,24,48,732,186,'fig-code');text(s,44,78,'/app/task_file/output_data/','fig-mono');
  line(s,53,92,53,211);line(s,53,112,72,112);line(s,53,158,72,158);line(s,76,167,76,189);line(s,76,189,95,189);
  text(s,85,117,'plan_b1.jsonl','fig-mono');text(s,409,117,tr('已转入主工作区','Transferred to main'),'fig-good');source(s,300,690,117,select);
  text(s,85,163,'validator_reports/','fig-mono');text(s,108,194,'bucket2.json','fig-mono');text(s,409,194,tr('验证报告，非规划文件','Validation report, not a plan'),'fig-text');source(s,368,690,194,select);
  text(s,24,267,tr('桶 2 规划 (child-2)','Bucket 2 planner (child-2)'),'fig-label');text(s,409,267,tr('没有观察到 plan_b2.jsonl 的成功转移','No successful plan_b2.jsonl transfer recorded'),'fig-small');
  const start=c.events.find(e=>e.lane==='child-2'&&e.type==='child_started'),end=f.cancel;
  line(s,40,307,731,307);s.append(vector('circle',{cx:40,cy:307,r:6,class:'fig-dot'}),vector('circle',{cx:731,cy:307,r:6,class:'fig-dot fig-failed'}));
  text(s,24,337,formatTime(start.elapsed_ms),'fig-time');text(s,595,337,formatTime(end.elapsed_ms),'fig-time');source(s,428,709,337,select);
  text(s,24,295,tr('开始运行','Starts running'),'fig-small');text(s,680,295,tr('被取消','Cancelled'),'fig-small');
  text(s,24,371,tr('关闭流程取消未完成子任务','Shutdown cancels the unfinished child'),'fig-text');text(s,24,396,'initiated_by: scaffold_shutdown','fig-mono');
  line(s,24,416,756,416);text(s,24,447,'local_status: incomplete','fig-label');source(s,430,709,447,select);
  return s;
}

function compactFigure(title,height){
  const s=figure(title);s.setAttribute('viewBox',`0 0 320 ${height}`);s.classList.add('is-compact');return s;
}

function compactRevision(c,select){
  const tr=(_zh,en)=>en;
  const f=compactEvidence(c),s=compactFigure(tr('测试版本与新版本对照','Tested and current revisions'),550);
  text(s,8,25,tr('版本对照','Revision check'),'fig-heading');
  rect(s,8,47,144,193,'fig-green');rect(s,168,47,144,193,'fig-blue');
  text(s,20,76,tr('已测试','Tested'),'fig-label');text(s,180,76,tr('新版本','New heads'),'fig-label');
  source(s,165,100,103,select);source(s,195,260,103,select);
  f.heads.forEach((head,i)=>{
    const y=131+i*55;
    text(s,20,y,head.branch,'fig-small');text(s,180,y,head.branch,'fig-small');
    text(s,20,y+23,head.before.slice(0,12),'fig-hash');text(s,180,y+23,head.after.slice(0,12),'fig-hash');
    path(s,`M155 ${y+15}H165M161 ${y+11}L165 ${y+15}L161 ${y+19}`);
  });
  text(s,8,277,tr('比较版本','Compare revisions'),'fig-label');source(s,289,267,277,select);
  rect(s,8,293,304,62,'fig-code');text(s,20,317,'git diff f2ff20b..4f8b595','fig-mono');text(s,20,341,'-- bottle.py','fig-mono');
  line(s,22,389,22,513);
  const rows=[[303,389,tr('首次修改','Repair attempt'),'exit 128'],[315,451,'validation_test.py',''],[316,513,tr('重试命令','Retried command'),'exit 0']];
  for(const[seq,y,label,sub]of rows){s.append(vector('circle',{cx:22,cy:y-5,r:5,class:seq===303?'fig-dot fig-failed':'fig-dot'}));text(s,40,y,label,'fig-label');if(sub)text(s,40,y+22,sub,'fig-small');source(s,seq,267,y,select);}
  return s;
}

function compactRepeated(c,select){
  const tr=(_zh,en)=>en;
  const f=compactEvidence(c),s=compactFigure(tr('同一个完成结果的交付时间线','Delivery timeline for one completion'),590);
  text(s,8,25,f.completion,'fig-heading');text(s,226,25,'child-4','fig-small');
  line(s,21,74,21,494);
  const labels=[tr('首次到达','First arrival'),tr('首次呈现','First presentation'),'reject',tr('use（重放前）','use (before replay)'),tr('同一结果重放','Same result replayed'),tr('第二次呈现','Second presentation'),tr('再次 use','use again')];
  f.events.forEach((e,i)=>{
    const y=79+i*70;
    if(e.seq===722)rect(s,8,y-25,304,56,'fig-pink');
    s.append(vector('circle',{cx:21,cy:y-5,r:5,class:e.seq===722?'fig-dot fig-failed':'fig-dot'}));
    text(s,39,y,labels[i],'fig-label');text(s,39,y+24,formatTime(e.elapsed_ms),'fig-time');source(s,e.seq,267,y,select);
    const occurrence=e.seq===317?'occ-2':e.seq===754?'occ-5':'';
    if(occurrence)text(s,154,y+24,occurrence,'fig-mono');
  });
  text(s,8,557,tr('重放关联原交付','Replay of the original delivery'),'fig-small');text(s,8,581,'gateway-occ-2','fig-mono');
  return s;
}

function compactArtifacts(c,select){
  const tr=(_zh,en)=>en;
  const f=compactEvidence(c),s=compactFigure(tr('文件交付与未完成任务','File transfers and the unfinished task'),535);
  text(s,8,25,tr('主工作区收到的文件','Files in the workspace'),'fig-heading');text(s,8,58,'output_data/','fig-mono');
  line(s,22,72,22,214);line(s,22,103,36,103);line(s,22,168,36,168);
  text(s,40,108,'plan_b1.jsonl','fig-mono');text(s,40,133,tr('已转入','Transferred'),'fig-good');source(s,300,267,108,select);
  text(s,40,173,'validator_reports/','fig-mono');text(s,57,198,'bucket2.json','fig-mono');text(s,57,223,tr('验证报告','Validation report'),'fig-good');source(s,368,267,198,select);
  line(s,8,246,312,246);
  if(f.missingPlan){text(s,8,277,'plan_b2.jsonl','fig-mono');text(s,8,303,tr('未记录到成功转移','No successful transfer recorded'),'fig-small');}
  text(s,8,349,tr('规划子任务 child-2','Planner child-2'),'fig-label');
  const start=c.events.find(e=>e.lane==='child-2'&&e.type==='child_started');
  line(s,22,385,296,385);s.append(vector('circle',{cx:22,cy:385,r:5,class:'fig-dot'}),vector('circle',{cx:296,cy:385,r:5,class:'fig-dot fig-failed'}));
  text(s,8,373,tr('运行','Running'),'fig-small');text(s,221,373,tr('取消','Cancelled'),'fig-small');
  text(s,8,412,formatTime(start.elapsed_ms),'fig-time');text(s,224,412,formatTime(f.cancel.elapsed_ms),'fig-time');source(s,428,267,443,select);
  line(s,8,468,312,468);text(s,8,505,'incomplete','fig-heading');source(s,430,267,505,select);
  return s;
}

async function mount(host){
  const loading=node('p','evidence-status',tr('正在读取归档记录…','Loading archived records…'));loading.setAttribute('role','status');host.replaceChildren(loading);
  const bundle=await loadArchive(host.dataset.src,location.hostname,fetch);
  const initial=readEvidenceLocation(location.href,bundle.cases);
  let current=bundle.cases.find(c=>c.id===initial.caseId),selected=initial.seq,mode=initial.mode;
  let recordOpen=new URL(location.href).searchParams.has('event'),mapOpen=false;
  const compact=matchMedia('(max-width:640px)');
  const link=()=>evidenceLocation(location.href,{caseId:current.id,seq:selected,mode},Boolean(host.closest('[data-content-section]')));
  const remember=push=>history[push?'pushState':'replaceState'](history.state,'',link());
  function render(){
    host.replaceChildren();const tabs=node('div','evidence-tabs');tabs.setAttribute('role','group');tabs.setAttribute('aria-label',tr('选择案例','Select a case'));
    bundle.cases.forEach(c=>{const b=node('button','',tr(...names[c.id]));b.type='button';b.dataset.case=c.id;b.setAttribute('aria-pressed',String(c.id===current.id));b.addEventListener('click',()=>{if(current.id===c.id)return;current=c;selected=defaultEvents[c.id];mode='key';recordOpen=false;mapOpen=false;remember(true);render();host.querySelector(`[data-case="${c.id}"]`).focus({preventScroll:true});});tabs.append(b);});host.append(tabs);
    const heading=node('div','evidence-heading'),title=node(host.closest('[data-content-section]')?'h3':'h2','',tr(...titles[current.id])),identity=node('span','evidence-model',models[current.id][0]),icon=node('img','model-icon');icon.src=`/assets/model-icons/${models[current.id][1]}`;icon.alt='';identity.prepend(icon);heading.append(title,identity);host.append(heading);
    const recordPanel=node('details','evidence-record-panel'),mapPanel=node('details','evidence-map-panel');
    recordPanel.open=recordOpen;mapPanel.open=mapOpen;
    recordPanel.append(node('summary','',tr('事件记录','Event record')));
    mapPanel.append(node('summary','',tr('证据图','Evidence map')));
    recordPanel.addEventListener('toggle',()=>{recordOpen=recordPanel.open;});
    mapPanel.addEventListener('toggle',()=>{mapOpen=mapPanel.open;});
    const visual=node('div','evidence-visual'),scroll=node('div','evidence-scroll'),detail=node('div','evidence-record');
    scroll.tabIndex=compact.matches?-1:0;scroll.setAttribute('role','region');scroll.setAttribute('aria-label',compact.matches?tr('案例图','Case figure'):tr('案例图，可横向滚动','Case figure, horizontally scrollable'));
    detail.tabIndex=-1;detail.setAttribute('aria-label',tr('当前事件记录','Selected event record'));
    const inspect=seq=>{recordOpen=true;recordPanel.open=true;select(seq,true);detail.focus({preventScroll:true});recordPanel.scrollIntoView({block:'nearest'});};
    const focus=node('div','evidence-focus');focus.lang='en';
    const art=node('img','evidence-scene');art.src=`/assets/scene-${current.id}.png`;art.alt='';art.width=1536;art.height=1024;
    const points=node('div','evidence-points');points.setAttribute('role','group');points.setAttribute('aria-label','Key evidence');
    for(const p of focusEvidence(current)){
      const button=node('button','focus-point');button.type='button';button.dataset.seq=p.seq;
      button.setAttribute('aria-label',`${p.label}: ${p.value}. Inspect event ${p.seq}`);
      button.append(node('span','focus-label',p.label),node('span','focus-value',p.value));
      button.addEventListener('click',()=>inspect(p.seq));points.append(button);
    }
    focus.append(art,points);host.append(focus);
    const draw=(compact.matches?{release:compactRevision,replay:compactRepeated,'early-stop':compactArtifacts}:{release:revision,replay:repeated,'early-stop':artifacts})[current.id]||observedSequence;scroll.append(draw(current,inspect));visual.append(scroll);
    mapPanel.append(visual);host.append(recordPanel);
    const nav=node('div','evidence-navigation'),scope=node('select'),jump=node('select'),prev=node('button','','←'),next=node('button','','→');
    prev.setAttribute('aria-label',tr('上一事件','Previous event'));next.setAttribute('aria-label',tr('下一事件','Next event'));
    scope.setAttribute('aria-label',tr('记录范围','Record scope'));jump.setAttribute('aria-label',tr('选择记录','Select a record'));
    for(const[value,a,b]of [['key','关键记录','Key records'],['all','全部展示记录','All displayed records']]){const o=node('option','',tr(a,b));o.value=value;scope.append(o);}scope.value=mode;
    function choices(){return mode==='all'?current.events:keyEvents(current);}
    function refreshNav(){jump.replaceChildren();for(const e of choices()){const m=current.milestones.find(x=>x.seq===e.seq),o=node('option','',`#${e.seq}  /  ${formatTime(e.elapsed_ms)}  /  ${m?txt(m.title):eventLabel(e.type,document.documentElement.lang)}`);o.value=e.seq;jump.append(o);}if(!choices().some(e=>e.seq===selected))selected=choices()[0].seq;jump.value=selected;}
    scope.addEventListener('change',()=>{mode=scope.value;refreshNav();select(selected,true);});jump.addEventListener('change',()=>select(Number(jump.value),true));
    const step=d=>{const events=choices(),i=events.findIndex(e=>e.seq===selected);select(events[Math.max(0,Math.min(events.length-1,i+d))].seq,true);};prev.addEventListener('click',()=>step(-1));next.addEventListener('click',()=>step(1));nav.append(scope,jump,prev,next);recordPanel.append(nav,detail);
    const permalink=node('a','evidence-permalink',tr('记录链接','Record link'));permalink.href=link();permalink.setAttribute('aria-label',tr('此条记录的链接，可复制分享','Permanent link to the selected record'));
    const recordState=node('span','sr-only');recordState.setAttribute('aria-live','polite');recordState.setAttribute('aria-atomic','true');host.append(recordState);
    const raw=node('details','record-json'),rawContent=node('pre'),context=node('p','record-context');
    raw.append(node('summary','',tr('事件 JSON','Event JSON')),rawContent,context);
    const provenance=node('div','evidence-provenance');
    provenance.append(node('p','',`${current.episode_id} / ${current.events.length} of ${current.source_event_count} records`),node('p','source-hash',`SHA-256 ${current.source_sha256}`));
    const archive=node('a','',tr('下载展示记录','Download displayed records'));archive.href=host.dataset.src;archive.download='trajectories.public.json';
    provenance.append(archive);raw.append(provenance,mapPanel);
    const tools=node('div','evidence-record-tools');tools.append(permalink,raw);recordPanel.append(tools);
    function select(seq,updateLocation=false){
      const e=current.events.find(x=>x.seq===seq);if(!e)return;selected=seq;
      detail.replaceChildren();
      const milestone=current.milestones.find(x=>x.seq===seq),excerpt=recordPreview(e);
      const preview=node('pre','record-content',excerpt.text);preview.setAttribute('aria-label',tr('记录摘录','Record excerpt'));detail.append(preview);
      rawContent.textContent=JSON.stringify(e,null,2);
      context.textContent=milestone?txt(milestone.note):'';context.hidden=!milestone;
      host.querySelectorAll('.figure-source,.focus-point').forEach(n=>{const active=Number(n.dataset.seq)===seq;n.classList.toggle('selected',active);n.setAttribute('aria-pressed',String(active));});
      if(jump.querySelector(`option[value="${seq}"]`))jump.value=seq;
      const events=choices(),i=events.findIndex(x=>x.seq===seq);prev.disabled=i<=0;next.disabled=i===events.length-1;
      permalink.href=link();
      if(updateLocation){remember(false);recordState.textContent=tr(`当前事件 ${seq}`,`Current event ${seq}`);}
    }
    refreshNav();select(selected);
  }
  render();document.dispatchEvent(new Event('evidence-ready'));document.addEventListener('site-language-change',render);
  compact.addEventListener('change',render);
  addEventListener('popstate',()=>{
    const state=readEvidenceLocation(location.href,bundle.cases);
    const open=new URL(location.href).searchParams.has('event');
    if(state.caseId===current.id&&state.seq===selected&&state.mode===mode&&recordOpen===open)return;
    current=bundle.cases.find(c=>c.id===state.caseId);selected=state.seq;mode=state.mode;recordOpen=open;mapOpen=false;render();
  });
}

function showLoadError(host){
  const message=node('p','evidence-status');message.setAttribute('role','status');
  const retry=node('button','evidence-retry');retry.type='button';
  const download=node('a','evidence-download');download.href=host.dataset.src;
  const relabel=()=>{
    message.textContent=tr('案例记录暂时无法读取。','Case records could not be loaded.');
    retry.textContent=tr('重新读取','Try again');
    download.textContent=tr('查看归档 JSON','View archive JSON');
  };
  relabel();document.addEventListener('site-language-change',relabel);
  retry.addEventListener('click',()=>{document.removeEventListener('site-language-change',relabel);retry.disabled=true;mount(host).catch(()=>showLoadError(host));});host.replaceChildren(message,retry,download);
  document.dispatchEvent(new Event('evidence-ready'));
}
if(typeof document!=='undefined')document.querySelectorAll('[data-evidence-view]').forEach(host=>mount(host).catch(()=>showLoadError(host)));
