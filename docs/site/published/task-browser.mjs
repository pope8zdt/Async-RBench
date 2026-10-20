export function matchingTasks(tasks,{query='',source='',difficulty=''}={}){const q=query.trim().toLocaleLowerCase();return tasks.filter(t=>(!q||`${t.id} ${t.title}`.toLocaleLowerCase().includes(q))&&(!source||t.source===source)&&(!difficulty||t.difficulty===difficulty));}
export function pageSlice(items,page,size=12){const pages=Math.max(1,Math.ceil(items.length/size));page=Math.max(1,Math.min(page,pages));return{items:items.slice((page-1)*size,page*size),page,pages,total:items.length};}
export function selectedRecord(cases,id,seq){const c=cases.find(c=>c.id===id)||cases[0];return{case:c,event:c.events.find(e=>e.seq===Number(seq))||c.events[0]};}
export function resetTaskFilters(event,fields,render){event.preventDefault();fields.forEach(field=>{field.value='';});render();}

function mount(){
  const tr=(en,zh)=>document.documentElement.lang==='zh'?zh:en,lang=()=>document.documentElement.lang==='zh'?'zh':'en';
  const rows=[...document.querySelectorAll('[data-task]')],tasks=rows.map(row=>({id:row.dataset.task,title:row.querySelector('h3').textContent,source:row.dataset.source,difficulty:row.dataset.difficulty}));
  const form=document.querySelector('.task-filters'),query=document.getElementById('task-search'),source=document.getElementById('task-source'),difficulty=document.getElementById('task-difficulty');let page=1;
  function render(){const filtered=matchingTasks(tasks,{query:query.value,source:source.value,difficulty:difficulty.value}),slice=pageSlice(filtered,page);page=slice.page;const visible=new Set(slice.items.map(t=>t.id));rows.forEach(row=>{row.hidden=!visible.has(row.dataset.task);});document.getElementById('task-count').textContent=tr(`${filtered.length} / ${tasks.length} tasks`,`${filtered.length} / ${tasks.length} 个任务`);document.getElementById('task-empty').hidden=filtered.length>0;document.querySelector('.task-pager').hidden=slice.pages<2;document.getElementById('previous-page').disabled=page===1;document.getElementById('next-page').disabled=page===slice.pages;document.getElementById('page-count').textContent=`${page} / ${slice.pages}`;}
  form.addEventListener('submit',event=>event.preventDefault());form.addEventListener('input',()=>{page=1;render();});form.addEventListener('change',()=>{page=1;render();});form.addEventListener('reset',event=>resetTaskFilters(event,[query,source,difficulty],()=>{page=1;render();}));
  for(const[id,step]of[['previous-page',-1],['next-page',1]])document.getElementById(id).addEventListener('click',()=>{page+=step;render();document.getElementById('catalog').scrollIntoView({block:'start'});});
  document.addEventListener('site-language-change',render);render();
  const host=document.querySelector('[data-archive-url]'),caseSelect=document.getElementById('record-case'),eventSelect=document.getElementById('record-event'),detail=document.getElementById('record-detail');let cases=null;
  const node=(tag,text,cls)=>{const n=document.createElement(tag);n.textContent=text;if(cls)n.className=cls;return n;};
  function drawRecord(updateURL=false){
    if(!cases)return;const selected=selectedRecord(cases,caseSelect.value,eventSelect.value),c=selected.case,e=selected.event;
    const milestone=c.milestones.find(m=>m.seq===e.seq),label=milestone?.title?.[lang()]||e.type;
    detail.replaceChildren(node('h3',label),node('p',`${c.model} · ${c.episode_id} · #${e.seq}`,'record-meta'));
    if(milestone?.note?.[lang()])detail.append(node('p',milestone.note[lang()]));
    detail.append(node('pre',JSON.stringify(e,null,2),'record-raw'));
    if(updateURL){const u=new URL(location.href);u.searchParams.set('case',c.id);u.searchParams.set('seq',String(e.seq));u.hash='records';history.replaceState(null,'',u);}
  }
  function caseChanged(seq,updateURL=false){const c=cases.find(c=>c.id===caseSelect.value)||cases[0];eventSelect.replaceChildren(...c.events.map(e=>{const n=node('option',`#${e.seq} · ${c.milestones.find(m=>m.seq===e.seq)?.title?.[lang()]||e.type}`);n.value=e.seq;return n;}));if(c.events.some(e=>e.seq===Number(seq)))eventSelect.value=seq;eventSelect.disabled=false;drawRecord(updateURL);}
  caseSelect.addEventListener('change',()=>caseChanged(null,true));eventSelect.addEventListener('change',()=>drawRecord(true));
  document.addEventListener('site-language-change',()=>{if(cases){for(const option of caseSelect.options)option.textContent=cases.find(c=>c.id===option.value).title[lang()];caseChanged(eventSelect.value);}});
  fetch(host.dataset.archiveUrl,{credentials:'omit'}).then(async response=>{if(!response.ok)throw Error();const data=await response.json();if(data.publication!=='reviewed-excerpts-v1'||!Array.isArray(data.cases)||data.cases.length!==6||data.cases.some(c=>!c.events?.length||!Array.isArray(c.milestones)))throw Error();cases=data.cases;const u=new URL(location.href),s=selectedRecord(cases,u.searchParams.get('case'),u.searchParams.get('seq'));caseSelect.value=s.case.id;caseChanged(s.event.seq);}).catch(()=>{detail.textContent=tr('Archived records could not be loaded. Please reload the page.','归档记录无法载入，请刷新页面重试。');caseSelect.disabled=true;});
}
if(typeof document!=='undefined')mount();
