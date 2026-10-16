// Progressive enhancement: no JavaScript leaves every original explanation readable.
export function disclosureState(state={open:false,pinned:false,suppressed:false}, action) {
  if(action==='click') return state.pinned ? {open:false,pinned:false,suppressed:true} : {open:true,pinned:true,suppressed:false};
  if(action==='escape'||action==='dismiss') return {open:false,pinned:false,suppressed:true};
  if(action==='enter') return {...state,open:true,suppressed:false};
  if(action==='focus') return state.suppressed ? state : {...state,open:true};
  if(action==='leave') return state.pinned ? state : {open:false,pinned:false,suppressed:false};
  return state;
}

export function popupPosition(rect,width,height,viewportWidth,viewportHeight) {
  return {left:Math.max(12,Math.min(rect.left,viewportWidth-width-12)),
    top:rect.bottom+8+height<=viewportHeight-12 ? rect.bottom+8 : Math.max(12,rect.top-height-8)};
}

// Pointer hover must not inherit a stale mouse focus. Keyboard users can keep
// reading the preview while moving focus from the trigger into its content.
export const keepPeekFocus=(active,button,panel)=>Boolean(active?.matches(':focus-visible')&&(active===button||panel.contains(active)));

export const cleanProse = text => text.replace(/\s*·\s*/g,'\u2002 ');
const bilingual=(zh,en)=>{const fragment=document.createDocumentFragment();for(const[lang,value]of [['zh',zh],['en',en]]){const span=document.createElement('span');span.className='i18n';span.lang=lang;span.textContent=value;fragment.append(span);}return fragment;};
let serial=0;

function makePeek(content,zh,en,labelNode,triggerHost) {
  if(!content||content.closest('.compact-peek,.peek-panel'))return;
  const wrapper=document.createElement('div');wrapper.className='compact-peek';
  const button=document.createElement('button');button.className='peek-trigger';button.type='button';
  const panel=document.createElement('div');panel.className='peek-panel';panel.id=`peek-${++serial}`;
  panel.setAttribute('popover','auto');panel.setAttribute('role','region');
  button.id=`peek-label-${serial}`;button.setAttribute('aria-controls',panel.id);button.setAttribute('aria-expanded','false');panel.setAttribute('aria-labelledby',button.id);
  button.append(labelNode || bilingual(zh,en));const mark=document.createElement('span');mark.className='peek-mark';mark.setAttribute('aria-hidden','true');button.append(mark);
  content.replaceWith(wrapper);wrapper.append(button,panel);panel.append(content);
  const toolbar=document.createElement('div');toolbar.className='peek-toolbar';
  const title=document.createElement('strong');title.append(labelNode?labelNode.cloneNode(true):bilingual(zh,en));
  const close=document.createElement('button');close.type='button';close.className='peek-close';close.textContent='×';close.setAttribute('aria-label','关闭详情 / Close details');
  toolbar.append(title,close);panel.prepend(toolbar);
  let state=disclosureState(),timer;
  const position=()=>{const p=popupPosition(button.getBoundingClientRect(),panel.offsetWidth,panel.offsetHeight,document.documentElement.clientWidth,innerHeight);panel.style.left=p.left+'px';panel.style.top=p.top+'px';};
  const isOpen=()=>panel.matches(':popover-open');
  const update=action=>{clearTimeout(timer);state=disclosureState(state,action);button.setAttribute('aria-expanded',String(state.open));
    if(state.open){if(!isOpen())panel.showPopover();position();}else if(isOpen())panel.hidePopover();};
  const leave=()=>{clearTimeout(timer);timer=setTimeout(()=>{if(!keepPeekFocus(document.activeElement,button,panel))update('leave');},180);};
  for(const element of [button,panel]) {
    element.addEventListener('pointerenter',event=>{if(event.pointerType==='mouse')update('enter');});
    element.addEventListener('pointerleave',leave);
    element.addEventListener('focusout',leave);
    element.addEventListener('keydown',event=>{if(event.key==='Escape'){event.preventDefault();update('escape');button.focus({preventScroll:true});}});
  }
  button.addEventListener('focus',()=>{if(button.matches(':focus-visible'))update('focus');});
  button.addEventListener('click',()=>update('click'));
  close.addEventListener('click',()=>{update('dismiss');button.focus({preventScroll:true});});
  panel.addEventListener('toggle',()=>{if(!isOpen()){state=disclosureState(state,'dismiss');button.setAttribute('aria-expanded','false');}});
  panel.addEventListener('beforetoggle',event=>{if(event.newState==='open')queueMicrotask(position);});
  if(triggerHost)triggerHost.append(button);
  return wrapper;
}

function sectionDetails(section, zh, en) {
  if(!section||section.tagName==='DETAILS'||section.closest('[data-participation]'))return;
  const detail=document.createElement('details');detail.className='compact-section';
  if(section.id){detail.id=section.id;section.removeAttribute('id');}
  const summary=document.createElement('summary');const heading=section.querySelector('h2,h3');
  const number=section.querySelector('.usage-step-no');if(number)summary.append(number);
  if(zh)summary.append(bilingual(zh,en));else if(heading)while(heading.firstChild)summary.append(heading.firstChild);
  heading?.remove();section.replaceWith(detail);detail.append(summary,section);
  return detail;
}

function cleanSeparators(root) {
  const walker=document.createTreeWalker(root,NodeFilter.SHOW_TEXT);const nodes=[];
  while(walker.nextNode())nodes.push(walker.currentNode);
  for(const node of nodes)if(node.textContent.includes('·')&&!node.parentElement.closest('script,style,pre,code,svg,.ambient,.record-content'))node.textContent=cleanProse(node.textContent);
}

function enhanceEvidence(host) {
  for(const element of host.querySelectorAll('.evidence-caption,.record-note'))makePeek(element,element.classList.contains('record-note')?'事件说明':'查看记录',element.classList.contains('record-note')?'Event context':'Inspect records');
  cleanSeparators(host);
}

function revealHash() {
  let id;try{id=decodeURIComponent(location.hash.slice(1));}catch{return;}
  const target=document.getElementById(id);if(!target)return;
  for(let node=target;node;node=node.parentElement)if(node.tagName==='DETAILS')node.open=true;
  requestAnimationFrame(()=>target.scrollIntoView({block:'start'}));
}

function collectSectionNotes() {
  const chapters=[...document.querySelectorAll('.research-chapter')];
  const scopes=chapters.length?chapters:[document.querySelector('main')].filter(Boolean);
  for(const scope of scopes) {
    const notes=[...scope.querySelectorAll(':scope > .compact-peek, .page-heading > .compact-peek, .usage-intro > .compact-peek, .ranking-section > .compact-peek, #scenarios > .compact-peek, .catalog-caption > .compact-peek, .evidence-page > .section > .compact-peek')];
    if(!notes.length)continue;
    const detail=document.createElement('details');detail.className='section-notes';
    const summary=document.createElement('summary');const labels={framework:['关于框架','About the framework'],tasks:['任务来源与版本','Sources and version'],leaderboard:['结果口径','About these results'],trajectories:['记录来源','About the records']};summary.append(bilingual(...(labels[scope.id]||['来源与说明','Sources and context'])));detail.append(summary);
    const contents=document.createElement('div');contents.className='section-note-links';
    contents.append(...notes);detail.append(contents);scope.append(detail);
  }
}

function mount() {
  cleanSeparators(document.body);
  if(document.body.dataset.section==='entry')return;
  const family=document.body.dataset.section;
  const hasFamily=name=>family===name||!!document.querySelector(`[data-content-section="${name}"]`);
  const backdrop=document.querySelector('.edition-backdrop');
  if(backdrop&&!backdrop.classList.contains('margin-motion')){backdrop.replaceChildren();for(const[name,cls]of [['profile','context-code'],['revision','context-revision'],['replay','context-replay'],['artifacts','context-files']]){const img=document.createElement('img');img.src=`/assets/context/${name}.svg`;img.alt='';img.className=cls;img.draggable=false;backdrop.append(img);}}
  // Only secondary prose becomes a small, accessible detail. Never move data controls or raw records.
  const labels=[['.source-note','论文来源','Paper source'],['.ranking-caption','统计口径','Statistics'],['.result-note','指标说明','Metric notes'],['.dataset-summary','任务构成','Task composition'],['.diagram-key','流程说明','About this diagram'],['.page-heading > .lead','概述','About'],['.usage-intro > .usage-description','测评目标','Evaluation scope']];
  if(typeof HTMLElement.prototype.showPopover==='function') {
    for(const[selector,zh,en]of labels)for(const element of document.querySelectorAll(selector))makePeek(element,zh,en);
    for(const selector of ['.source-note','.dataset-summary'])for(const note of document.querySelectorAll(selector)) {
      const scope=note.closest('[data-content-section]')||document;
      const heading=scope.querySelector('.page-heading'),peek=note.closest('.compact-peek');
      if(heading&&peek)heading.append(peek);
    }
    for(const group of document.querySelectorAll('.usage-metrics > div, #scenarios .definition-list > div')) {
      const term=group.querySelector('dt'),description=group.querySelector('dd');if(!term||!description)continue;
      const label=document.createElement('span');while(term.firstChild)label.append(term.firstChild);
      const content=document.createElement('div');while(description.firstChild)content.append(description.firstChild);description.append(content);
      makePeek(content,'','',label,term);
    }
    if(family==='overview') {
      const headline=document.querySelector('.usage-headline');if(headline)makePeek(headline,'动态调整','Dynamic replanning');
      const groups=[['.usage-start > div:first-child','开始测评','Run evaluation'],['.usage-explore > div:first-child','八类场景','Eight scenarios'],['.usage-explore > div:last-child','真实案例','Recorded examples']];
      for(const[selector,zh,en]of groups) {
        const group=document.querySelector(selector),heading=group?.querySelector('h2'),p=group?.querySelector('p');
        if(heading&&p){heading.replaceChildren();makePeek(p,zh,en,undefined,heading);}
      }
      for(const p of document.querySelectorAll('.usage-start > div:last-child > p'))makePeek(p,'运行方式','Execution');
    }
    if(hasFamily('trajectories'))for(const p of document.querySelectorAll('.evidence-page > .section > p'))makePeek(p,'运行设置','Runtime settings');
    if(family==='run')for(const p of document.querySelectorAll('.page-heading > p,.fine'))makePeek(p,'结果说明','Result notes');
    if(hasFamily('tasks')) {
      makePeek(document.querySelector('#scenarios > p'),'场景分布','Scenario counts');
      makePeek(document.querySelector('.catalog-caption > span'),'浏览说明','Browsing');
      const catalog=document.getElementById('task-rows');
      const compactRows=()=>{for(const id of catalog.querySelectorAll('.case-id'))makePeek(id,'任务编号','Task ID');cleanSeparators(catalog);};
      if(catalog){const observer=new MutationObserver(()=>{observer.disconnect();compactRows();observer.observe(catalog,{childList:true,subtree:true});});compactRows();observer.observe(catalog,{childList:true,subtree:true});}
      if(family==='tasks'){const notes=document.querySelector('#scenarios + section');if(notes)sectionDetails(notes,'发布说明','Release notes');}
    }
    if(hasFamily('leaderboard'))for(const paragraph of document.querySelectorAll('.section article > p'))makePeek(paragraph,'实验说明','Study notes');
  }
  if(hasFamily('guide')) {
    for(const[id,zh,en]of [['installation','安装框架','Install'],['preparation','模型与 judge','Model & judge'],['running','运行任务','Run'],['results','查看结果','Read results']])sectionDetails(document.getElementById(id),zh,en);
    sectionDetails(document.querySelector('.usage-field-section'),'结果字段','Result fields');
    sectionDetails(document.getElementById('scale'),'扩大评测范围','Scale up');
    sectionDetails(document.getElementById('sharing'),'提交结果','Share results');
  }
  if(family==='protocol')for(const section of document.querySelectorAll('main > section.section'))if(section.querySelector('h2'))sectionDetails(section);
  collectSectionNotes();
  document.querySelectorAll('[data-evidence-view]').forEach(host=>{
    if(typeof HTMLElement.prototype.showPopover!=='function')return;
    // Disconnect while moving nodes to avoid observing our own mutations.
    const observer=new MutationObserver(()=>{observer.disconnect();enhanceEvidence(host);observer.observe(host,{childList:true,subtree:true});});
    enhanceEvidence(host);observer.observe(host,{childList:true,subtree:true});
  });
  document.addEventListener('site-language-change',()=>{cleanSeparators(document.body);document.querySelectorAll('.peek-panel:popover-open').forEach(panel=>panel.hidePopover());});
  let positionFrame;
  const reposition=()=>{cancelAnimationFrame(positionFrame);positionFrame=requestAnimationFrame(()=>{
    for(const panel of document.querySelectorAll('.peek-panel:popover-open')) {
      const button=document.getElementById(panel.getAttribute('aria-labelledby'));
      const rect=button?.getBoundingClientRect();
      if(!rect||rect.bottom<0||rect.top>innerHeight){panel.hidePopover();continue;}
      const p=popupPosition(rect,panel.offsetWidth,panel.offsetHeight,document.documentElement.clientWidth,innerHeight);
      panel.style.left=p.left+'px';panel.style.top=p.top+'px';
    }
  });};
  addEventListener('resize',reposition);
  document.addEventListener('scroll',reposition,{capture:true,passive:true});
  addEventListener('hashchange',revealHash);revealHash();
  document.documentElement.classList.add('compact-ready');
}

if(typeof document!=='undefined')mount();
