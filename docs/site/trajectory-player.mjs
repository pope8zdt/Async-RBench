import { displayedEvents, stepIndex, eventPosition, laneState, completionState, recordExcerpt } from './trajectory-logic.mjs';

const language = () => document.documentElement.lang === 'en' ? 'en' : 'zh';
const choose = (zh, en) => language() === 'zh' ? zh : en;
const label = value => value[language()];
const clock = ms => `${String(Math.floor(ms / 60000)).padStart(2, '0')}:${(ms / 1000 % 60).toFixed(1).padStart(4, '0')}`;
const names = {
  episode_started:['运行开始','Episode starts'], episode_ended:['运行结束','Episode ends'],
  child_spawned:['创建子任务','Child spawned'], child_started:['子任务开始','Child starts'],
  child_completed:['子任务返回','Child completes'], child_cancelled:['子任务取消','Child cancelled'],
  child_failed:['子任务失败','Child fails'], result_available:['结果可用','Result available'],
  result_delivered:['结果到达','Result arrives'], result_presented:['呈现给主代理','Presented to main'],
  adapter_queued:['进入呈现队列','Queued for presentation'],
  result_delivery_evaluator_fact:['交付关联记录','Delivery linkage'],
  main_action:['主代理动作','Main-agent action'], main_action_finished:['动作结束','Action finishes'],
  child_path_promotion_result:['文件转移结果','File-promotion result'], finish_invoked:['调用结束工具','Finish invoked'],
};
const states = {pending:['未开始','Not started'],running:['运行中','Running'],completed:['已返回','Returned'],cancelled:['已取消','Cancelled'],failed:['失败','Failed']};
const workNames = {
  security_patch:['安全补丁','Security patch'],sanitize_history:['仓库清理','Repository cleanup'],release_infrastructure:['部署准备','Deployment setup'],
  bucket1_optimizer:['桶 1 规划','Bucket 1 planner'],bucket2_optimizer:['桶 2 规划','Bucket 2 planner'],global_shape_allocator:['共享形状分配','Shared shape allocator'],
  bucket1_validator:['桶 1 验证','Bucket 1 validator'],bucket2_validator:['桶 2 验证','Bucket 2 validator'],
};
const models = {'gpt-5.6-terra':['GPT-5.6 Terra','openai.svg'],'claude-sonnet-5':['Claude Sonnet 5','claude-color.svg'],'qwen3.5-27b':['Qwen3.5 27B','qwen-color.svg']};
const caseTitles = {release:['安全补丁与版本更新','Patch and revision'],replay:['结果重复呈现','Repeated delivery'],'early-stop':['工作流提前结束','Early termination']};
const caseTitle = c => caseTitles[c.id] ? choose(...caseTitles[c.id]) : label(c.title);
const node = (tag, className, text) => { const e=document.createElement(tag); if(className)e.className=className; if(text!==undefined)e.textContent=text; return e; };
const button = (text, className, onClick) => { const b=node('button',className,text); b.type='button'; b.addEventListener('click',onClick); return b; };
const title = e => choose(...(names[e.type] || [e.type,e.type]));

export async function mountTrajectoryPlayer() {
  const host = document.getElementById('trajectory-player');
  // The preview build is deliberately usable only on loopback, never a published host.
  if (!['localhost','127.0.0.1','[::1]'].includes(location.hostname)) {
    host.replaceChildren(node('p','trace-loading',choose('轨迹仅供本地预览。','Trajectories are local-preview only.')));
    return;
  }
  let bundle;
  try {
    const response=await fetch(host.dataset.src);
    if (!response.ok) throw new Error('Unavailable replay data');
    bundle=await response.json();
    if (!bundle.local_only || !bundle.cases?.length) throw new Error('Invalid replay bundle');
  } catch {
    host.replaceChildren(node('p','trace-loading',choose('本地回放数据未能加载，请重新构建并刷新页面。','Local replay data could not load. Rebuild the preview and refresh.')));
    return;
  }
  let caseIndex=0, mode='key', index=0, playing=false, speed=1, timer=null;
  const currentCase=()=>bundle.cases[caseIndex];
  const sequence=()=>displayedEvents(currentCase(),mode);
  const currentEvent=()=>sequence()[index];
  const stop=()=>{playing=false;clearTimeout(timer);timer=null;};
  const tabs=node('div','trace-tabs'); tabs.setAttribute('role','tablist'); tabs.setAttribute('aria-label','Trajectory cases');
  const panel=node('div','trace-panel'); panel.id='trace-panel'; panel.setAttribute('role','tabpanel');
  const intro=node('div','trace-intro');
  const timeline=node('div','trace-timeline');
  const controls=node('div','trace-controls');
  const moments=node('div','trace-moments');
  const detail=node('div','trace-detail');
  const source=node('details','trace-source');
  const live=node('span','sr-only'); live.setAttribute('role','status'); live.setAttribute('aria-live','polite');
  const reading=node('div','trace-reading');reading.append(detail,moments);
  panel.append(intro,controls,reading,timeline,source,live);
  host.replaceChildren(tabs,panel);
  // Reading a record pauses playback so the next frame cannot remove keyboard focus.
  detail.addEventListener('focusin',()=>{if(playing){stop();updatePlayButton();}});

  function schedule() {
    clearTimeout(timer);
    if(!playing)return;
    // Presentation cadence, not a simulation of agent compute. Source times never change.
    timer=setTimeout(()=>{
      if(index>=sequence().length-1){stop();renderFrame();return;}
      index++; if(index>=sequence().length-1) stop();
      renderFrame();schedule();
    },(mode==='key'?2400:700)/speed);
  }
  function move(target, announce=true) {
    stop(); index=Math.max(0,Math.min(sequence().length-1,target)); renderFrame();
    if(announce) announceEvent();
  }
  function announceEvent() { live.textContent=`#${currentEvent().seq} ${title(currentEvent())}, ${clock(currentEvent().elapsed_ms)}`; }
  function seekSeq(seq) {
    if(!sequence().some(e=>e.seq===seq)) mode='all';
    index=sequence().findIndex(e=>e.seq===seq);stop();renderControls();renderFrame();announceEvent();
  }
  function laneLabel(lane) {
    if(lane.id==='main')return choose('主代理','Main agent');
    if(lane.id==='delivery')return choose('结果交付','Result delivery');
    const work=workNames[lane.label];
    return work?choose(...work):lane.label.startsWith('requirement_worker_')?choose(`需求工作流 ${lane.label.slice(-2)}`,`Requirement stream ${lane.label.slice(-2)}`):lane.label;
  }
  function renderTabs() {
    tabs.replaceChildren(...bundle.cases.map((c,i)=>{
      const b=button(caseTitle(c),'trace-tab',()=>{
        stop();caseIndex=i;index=0;mode='key';render();
        tabs.children[i].focus();
      });
      b.id=`trace-tab-${i}`;b.setAttribute('role','tab');b.setAttribute('aria-controls','trace-panel');
      b.setAttribute('aria-selected',String(i===caseIndex));b.tabIndex=i===caseIndex?0:-1;
      b.addEventListener('keydown',event=>{
        let next;
        if(event.key==='ArrowRight')next=(i+1)%bundle.cases.length;
        if(event.key==='ArrowLeft')next=(i+bundle.cases.length-1)%bundle.cases.length;
        if(event.key==='Home')next=0;
        if(event.key==='End')next=bundle.cases.length-1;
        if(next!==undefined){event.preventDefault();tabs.children[next].click();}
      }); return b;
    }));
    panel.setAttribute('aria-labelledby',`trace-tab-${caseIndex}`);
  }
  function renderIntro() {
    const c=currentCase(); const heading=node('div');
    heading.append(node('h3','',caseTitle(c)),node('p','',label(c.description)));
    const identity=node('div','trace-identity');
    const model=models[c.model];
    if(model){const icon=node('img','model-icon');icon.src=`${document.body.dataset.base}/assets/model-icons/${model[1]}`;icon.alt='';icon.width=28;icon.height=28;identity.append(icon);}
    identity.append(node('strong','',model?.[0]||c.model),node('span','trace-mode','Async'),node('span','trace-duration',`${clock(c.events.at(-1).elapsed_ms)} ${choose('原始耗时','recorded')}`));
    intro.replaceChildren(heading,identity);
  }
  function renderTimeline() {
    const c=currentCase(),duration=c.events.at(-1).elapsed_ms;
    const chart=node('div','trace-lanes');
    const keys=new Set(c.milestones.map(m=>m.seq));
    for(const [i,lane] of c.lanes.entries()){
      const row=node('div','trace-lane'); row.dataset.lane=lane.id;row.style.setProperty('--lane-index',i);
      const labelNode=node('div','trace-lane-label');labelNode.append(node('strong','',laneLabel(lane)));
      if(lane.id.startsWith('child'))labelNode.append(node('span','trace-lane-state',lane.id));
      const rail=node('div','trace-rail');
      const laneEvents=c.events.filter(e=>e.lane===lane.id);
      const start=laneEvents.find(e=>e.type==='child_started');
      const end=laneEvents.find(e=>['child_completed','child_cancelled','child_failed'].includes(e.type));
      if(start){const bar=node('span','trace-work-span');bar.style.left=`${eventPosition(start,duration)}%`;bar.style.width=`${Math.max(0,eventPosition(end||c.events.at(-1),duration)-eventPosition(start,duration))}%`;rail.append(bar);}
      for(const event of laneEvents){
        const dot=button('',`trace-dot${keys.has(event.seq)?' is-key':''}`,()=>seekSeq(event.seq));
        dot.style.left=`${eventPosition(event,duration)}%`;dot.dataset.seq=event.seq;
        dot.title=`#${event.seq} · ${clock(event.elapsed_ms)} · ${title(event)}`;dot.setAttribute('aria-label',dot.title);
        // All records remain reachable by the event selector; key nodes are keyboard stops.
        dot.tabIndex=keys.has(event.seq)?0:-1;rail.append(dot);
      }
      rail.append(node('span','trace-cursor'));row.append(labelNode,rail);chart.append(row);
    }
    const axis=node('div','trace-axis');axis.append(node('span','','00:00'),node('span','',clock(duration/2)),node('span','',clock(duration)));
    const legend=node('p','trace-legend',choose('并发时间线 · 横轴为原始耗时，色带为子任务执行区间。点击节点查看记录。','Concurrent execution · original elapsed time; bands mark child execution intervals. Select a point to inspect.'));
    timeline.replaceChildren(chart,axis,legend);
  }
  let playButton,previous,next,range,counter,eventSelect,modeSelect;
  function renderControls() {
    playButton=button('', 'trace-play',()=>{if(playing)stop();else{if(index===sequence().length-1)index=0;playing=true;}renderFrame();schedule();});
    previous=button('‹','trace-step',()=>move(stepIndex(index,-1,sequence().length)));previous.setAttribute('aria-label',choose('上一事件','Previous event'));
    next=button('›','trace-step',()=>move(stepIndex(index,1,sequence().length)));next.setAttribute('aria-label',choose('下一事件','Next event'));
    range=node('input','trace-scrubber');range.type='range';range.min=0;range.step=1;range.setAttribute('aria-label',choose('回放位置（事件顺序）','Replay position (event order)'));
    range.addEventListener('input',()=>move(Number(range.value),false));
    counter=node('output','trace-counter');
    const modeLabel=node('label','trace-select-label',choose('内容','View'));
    modeSelect=node('select'); for(const [value,text] of [['key',choose('关键节点','Key moments')],['all',choose('全部展示事件','All displayed events')]]){const opt=node('option','',text);opt.value=value;modeSelect.append(opt);}modeSelect.value=mode;
    modeSelect.addEventListener('change',()=>{const seq=currentEvent().seq;stop();mode=modeSelect.value;const items=sequence();const nearest=items.findIndex(e=>e.seq>=seq);index=nearest<0?items.length-1:nearest;renderControls();renderFrame();modeSelect.focus();announceEvent();});modeLabel.append(modeSelect);
    const speedLabel=node('label','trace-select-label',choose('播放速度','Playback speed'));const speedSelect=node('select');
    for(const n of [0.5,1,2,4]){const opt=node('option','',`${n}×`);opt.value=n;speedSelect.append(opt);}speedSelect.value=speed;speedSelect.addEventListener('change',()=>{speed=Number(speedSelect.value);schedule();});speedLabel.append(speedSelect);
    const transport=node('div','trace-transport');transport.append(previous,playButton,next,range,counter);
    const options=node('div','trace-options');options.append(modeLabel,speedLabel);
    const eventLabel=node('label','trace-event-picker',choose('定位事件','Jump to event'));eventSelect=node('select');
    sequence().forEach((e,i)=>{const milestone=currentCase().milestones.find(m=>m.seq===e.seq);const o=node('option','',`#${e.seq} · ${clock(e.elapsed_ms)} · ${milestone?label(milestone.title):title(e)}`);o.value=i;eventSelect.append(o);});
    eventSelect.addEventListener('change',()=>move(Number(eventSelect.value)));eventLabel.append(eventSelect);
    eventLabel.hidden=mode==='key';
    controls.replaceChildren(transport,options,eventLabel);
  }
  function renderMoments() {
    moments.setAttribute('aria-label',choose('关键节点','Key moments'));
    moments.replaceChildren(...currentCase().milestones.map(m=>{
      const b=button(label(m.title),'trace-moment',()=>seekSeq(m.seq));b.dataset.seq=m.seq;
      b.prepend(node('span','',`#${m.seq} `));return b;
    }));
  }
  function renderDetail() {
    const c=currentCase(),e=currentEvent(),m=c.milestones.find(item=>item.seq===e.seq);
    const observation=node('article','trace-observation');
    observation.append(node('span','trace-eyebrow',`#${e.seq} / ${clock(e.elapsed_ms)}`),node('h4','',m?label(m.title):title(e)));
    if(m) observation.append(node('p','trace-annotation',label(m.note)));
    else observation.append(node('p','trace-annotation',choose('选中的归档事件。以下字段直接来自日志；未导出的字段不作推测。','Selected archived event. Fields below come from the log; omitted fields are not inferred.')));
    const excerpt=recordExcerpt(e);
    const excerptLabels={command:['命令原文','Recorded command'],excerpt:['命令节选','Command excerpt'],evidence:['记录中的证据字段','Recorded evidence'],fields:['记录字段','Recorded fields']};
    const excerptBox=node('div','trace-evidence');
    excerptBox.append(node('div','trace-evidence-label',choose(...excerptLabels[excerpt.kind])));
    const excerptText=node('pre');excerptText.tabIndex=0;excerptText.append(node('code','',excerpt.text));excerptBox.append(excerptText);observation.append(excerptBox);
    const rawDetails=node('details','trace-raw');rawDetails.open=detail.querySelector('.trace-raw')?.open||false;
    rawDetails.append(node('summary','',choose('查看事件 JSON','Event JSON')));
    const raw=node('pre','trace-record');raw.tabIndex=0;raw.append(node('code','',JSON.stringify({event_id:e.event_id,elapsed_ms:e.elapsed_ms,type:e.type,...e.record},null,2)));rawDetails.append(raw);observation.append(rawDetails);
    const state=node('aside','trace-observed-state');state.append(node('h4','',choose('截至此刻的记录','Recorded so far')));
    const completions=completionState(c.events,e.seq);
    if(!completions.length)state.append(node('p','',choose('尚无结果呈现记录。','No result presentation recorded yet.')));
    for(const completion of completions){const row=node('div','trace-completion');row.append(node('code','',completion.id),node('span','',choose(`已呈现 ${completion.presentations} 次`,`Presented ${completion.presentations}×`)),node('strong','',completion.decision||'—'));state.append(row);}
    const promotions=c.events.filter(item=>item.seq<=e.seq&&item.type==='child_path_promotion_result');
    const last=promotions.at(-1);
    if(last){state.append(node('h5','',choose('最近文件转移记录','Latest file-promotion record')));const p=node('pre','trace-artifact');p.append(node('code','',JSON.stringify({seq:last.seq,...last.record},null,2)));state.append(p);}
    const action=c.events.filter(item=>item.seq<=e.seq&&item.type==='main_action').at(-1);
    if(action){state.append(node('h5','',choose('最近主代理动作','Latest main-agent action')),node('p','trace-last-action',`#${action.seq} · ${action.record.kind}`));}
    state.append(node('p','trace-state-note',choose('呈现次数、确认决定与文件转移是不同证据；它们不自动等于任务成功。','Presentations, decisions and promotions are distinct observations, not automatic proof of task success.')));
    const stateDetails=node('details','trace-state-details');stateDetails.open=detail.querySelector('.trace-state-details')?.open||false;
    stateDetails.append(node('summary','',choose('截至此刻的状态记录','State recorded so far')),state);
    observation.append(stateDetails);detail.replaceChildren(observation);
  }
  function renderSource() {
    const c=currentCase();const summary=node('summary','',choose('记录来源与展示范围','Source & display scope'));
    const info=node('div');info.append(node('p','',c.episode_id),node('p','',`${c.source_name} · SHA-256 ${c.source_sha256}`),node('p','',choose(`原日志 ${c.source_event_count} 条，展示 ${c.events.length} 条。按事件播放，等待时间已压缩；时间线保留真实耗时和原工作流数量，不是当前配置的重跑。命令来自人工选取的原文片段；没有 stdout 的事件不补造输出。节点说明为阅读注释，不是模型思维过程。不包含私有判分逻辑，不重算论文分数。`,`Source: ${c.source_event_count} events; displayed: ${c.events.length}. Playback compresses idle time; the timeline retains original elapsed times and workflow counts, not a rerun of the current configuration. Commands are reviewed source excerpts; missing stdout is not reconstructed. Notes are editorial, not model reasoning. No private judging logic or recalculated paper scores.`)));
    source.replaceChildren(summary,info);
  }
  function updatePlayButton() {
    playButton.textContent=playing?choose('Ⅱ 暂停','Ⅱ Pause'):index===sequence().length-1?choose('↺ 重播','↺ Replay'):choose('▶ 播放','▶ Play');
    playButton.setAttribute('aria-pressed',String(playing));
  }
  function renderFrame() {
    const c=currentCase(),e=currentEvent();
    updatePlayButton();previous.disabled=index===0;next.disabled=index===sequence().length-1;
    range.max=sequence().length-1;range.value=index;range.setAttribute('aria-valuetext',`#${e.seq}, ${clock(e.elapsed_ms)}`);
    counter.textContent=`${index+1} / ${sequence().length}`;eventSelect.value=index;
    timeline.querySelectorAll('.trace-dot').forEach(dot=>{dot.classList.toggle('is-past',Number(dot.dataset.seq)<e.seq);dot.classList.toggle('is-current',Number(dot.dataset.seq)===e.seq);});
    timeline.querySelectorAll('.trace-cursor').forEach(cursor=>{cursor.style.left=`${eventPosition(e,c.events.at(-1).elapsed_ms)}%`;});
    for(const lane of c.lanes){const row=[...timeline.querySelectorAll('.trace-lane')].find(r=>r.dataset.lane===lane.id);const state=row.querySelector('.trace-lane-state');if(state){const status=laneState(c.events,lane.id,e.seq);state.textContent=`${lane.id} · ${choose(...states[status])}`;row.dataset.state=status;}}
    moments.querySelectorAll('button').forEach(b=>{b.classList.toggle('is-current',Number(b.dataset.seq)===e.seq);b.setAttribute('aria-pressed',String(Number(b.dataset.seq)===e.seq));});
    renderDetail();
  }
  function render(){renderTabs();renderIntro();renderTimeline();renderControls();renderMoments();renderSource();renderFrame();}
  document.addEventListener('site-language-change',()=>{render();});
  document.addEventListener('visibilitychange',()=>{if(document.hidden){stop();renderFrame();}});
  window.addEventListener('pagehide',stop);
  render();
}
