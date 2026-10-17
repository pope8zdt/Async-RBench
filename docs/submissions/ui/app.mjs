const root = document.querySelector('[data-submission-root]');
const find = selector => root.querySelector(selector);
const app = find('#submission-app');
const identity = find('#submission-identity');
const message = find('#submission-message');
let session, view = 'submit', bundle = null, validation = null, selected = null, items = [];
let generation = 0;
class StaleOperation extends Error {}
identity.disabled = true;
const escape = value => String(value ?? '').replace(/[&<>"']/g, char => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[char]));
const tr = (zh,en) => `<span class="i18n" lang="zh">${zh}</span><span class="i18n" lang="en">${en}</span>`;
const names = {pending:tr('待审核','Awaiting review'),approved:tr('已上榜','Listed'),changes_requested:tr('待修改','Changes requested'),rejected:tr('未通过','Rejected'),withdrawn:tr('已撤回','Withdrawn')};
const checks = {
  identity_and_settings:tr('身份与评测设置一致','Identity and settings match'),
  coverage_and_scores:tr('覆盖范围与分数已核对','Coverage and scores checked'),
  evidence_inspected:tr('已检查运行证据','Episode evidence inspected'),
  simulation_acknowledged:tr('仅为模拟数据，本地展示','Synthetic data, local listing only'),
};
const status = value => `<span class="status ${escape(value)}">${names[value] || escape(value)}</span>`;
const metrics = data => `<div class="metrics"><div><strong>${escape(data.episodes)}</strong><span>${tr('运行记录','Episodes')}</span></div><div><strong>${escape(data.drs)}</strong><span>DRS / 100</span></div><div><strong>${escape(data.success)}%</strong><span>${tr('任务成功率','Task success')}</span></div></div>`;
function tell(text, error=false){ message.textContent=text; message.className=error?'error':''; }
function announce(zh,en,error=false){tell(document.documentElement.lang==='zh'?zh:en,error);}
function report(error){if(!(error instanceof StaleOperation)){app.setAttribute('aria-busy','false');tell(error.message,true);}}
async function api(path, data){
  const started = generation;
  try {
    const response = await fetch(path,{method:data===undefined?'GET':'POST',credentials:'same-origin',headers:{'Content-Type':'application/json','X-CSRF-Token':session?.csrf || ''},body:data===undefined?undefined:JSON.stringify(data)});
    const result=await response.json();
    if(started!==generation) throw new StaleOperation();
    if(!response.ok) throw new Error(result.error || 'The request could not be completed.');
    return result;
  } catch(error) {
    if(started!==generation) throw new StaleOperation();
    throw error;
  }
}
async function refresh(){ items=session.role?(await api('/api/submissions')).items:[]; }
function entry(row){return `<div class="entry"><div class="entry-main"><h4>${escape(row.metadata.agent)}</h4><p class="muted small">${escape(row.metadata.model)} / r${row.revision}</p></div>${status(row.status)}<button class="text-button" data-open="${row.id}">${tr('查看','View')} →</button></div>`;}
function render(){
  root.querySelectorAll('[data-view]').forEach(button=>button.setAttribute('aria-current',button.dataset.view===view?'page':'false'));
  identity.value=session.role||'';
  app.setAttribute('aria-busy','false');
  if(view==='community'){renderCommunity().catch(report);return;}
  if(selected){renderDetail();return;}
  if(view==='review'){
    app.innerHTML=session.role==='maintainer'?`<div class="details-head"><h3>${tr('审核队列','Review queue')}</h3><span class="muted small">${items.filter(x=>x.status==='pending').length} ${tr('待审核','pending')}</span></div><div class="list">${items.map(entry).join('')||`<div class="empty">${tr('暂无提交。','No submissions yet.')}</div>`}</div>`:`<div class="empty">${tr('选择“维护者”模拟身份查看审核队列。','Choose the Maintainer demo identity to review submissions.')}</div>`;
    return;
  }
  const disabled=!session.role||session.role==='maintainer'?'disabled':'';
  app.innerHTML=`<div class="package-row"><h3>${tr('结果材料','Result package')}</h3><div class="actions"><label class="upload">${tr('上传 JSON','Upload JSON')}<input id="file" type="file" accept="application/json,.json" aria-label="Upload result package" ${disabled}></label><button id="sample" class="text-button" ${disabled}>${tr('试用示例','Try a sample')} →</button></div></div>
  ${disabled?`<p class="muted small">${tr('选择“参评者”模拟身份后提交。','Choose a Participant demo identity to submit.')}</p>`:''}
  ${validationMarkup()}
  <details><summary><span>${tr('我的提交','Your submissions')} (${items.length})</span></summary><div class="list">${items.map(entry).join('')||`<p class="muted">${tr('暂无提交。','No submissions yet.')}</p>`}</div></details>`;
}
function validationMarkup(){
  if(!validation) return '';
  if(!validation.valid) return `<div class="validation"><div><h4>${tr('请检查材料','Needs attention')}</h4><ul class="errors">${validation.errors.map(e=>`<li>${escape(e.message)}</li>`).join('')}</ul></div></div>`;
  return `<div class="validation"><div><h4>${escape(bundle.metadata.agent)}</h4><span class="success small">${tr('材料校验通过，等待人工审核','Package checks passed. Human review required.')}</span>${metrics(validation.metrics)}</div><button class="primary" id="submit">${tr('提交审核','Submit for review')} →</button></div>`;
}
async function prepare(value){bundle=value;validation=await api('/api/validate',{bundle});render();}
function renderDetail(){
  const row=selected, meta=row.bundle.metadata;
  const latest=row.history.filter(h=>h.actor==='maintainer').at(-1);
  app.innerHTML=`<div class="details-head"><h3>${escape(meta.agent)}</h3>${status(row.status)}</div><div class="split"><div>${metrics(row.validation.metrics)}
  <details><summary>${tr('材料与证据','Package & evidence')}</summary><dl class="meta"><div><dt>${tr('模型','Model')}</dt><dd>${escape(meta.model)}</dd></div><div><dt>${tr('机构','Organization')}</dt><dd>${escape(meta.organization)}</dd></div><div><dt>${tr('测评设置','Evaluation')}</dt><dd>Async / ${tr('一次重复','one repetition')}</dd></div><div><dt>${tr('修订','Revision')}</dt><dd>${row.revision} / ${tr('模拟','synthetic')}</dd></div><div><dt>${tr('代码版本','Code revision')}</dt><dd class="hash">${escape(meta.code_revision)}</dd></div><div><dt>${tr('材料指纹','Package hash')}</dt><dd class="hash">${row.hash}</dd></div></dl>
  <select id="episode" class="evidence-select" aria-label="Evidence episode">${row.bundle.evidence.map((e,i)=>`<option value="${i}">${escape(e.episode_id.replace(/^demo-/,''))}</option>`).join('')}</select><div id="event-visual"></div><button class="text-button" id="download">${tr('下载此修订','Download this revision')} ↓</button></details>
  <details><summary><span>${tr('审核记录','Review history')} (${row.history.length})</span></summary><ol class="history">${row.history.map(h=>`<li><time>${new Date(h.created).toLocaleString()}</time>${escape(h.actor)} — ${escape(h.action.replaceAll('_',' '))} / r${h.revision}${h.note?`<p>${escape(h.note)}</p>`:''}</li>`).join('')}</ol></details></div>
  <div>${latest?`<div class="review-note"><span class="muted small">${tr('最近审核意见','Latest decision')}</span><p>${escape(latest.note)}</p></div>`:''}${reviewMarkup(row)}</div></div><div class="back-row"><button id="back" class="text-button">← ${tr('返回','Back')}</button></div>`;
  drawEvidence(0);
}
function reviewMarkup(row){
  if(session.role==='maintainer'&&row.status==='pending') return `<h4>${tr('审核当前修订','Review this revision')}</h4><div class="checklist">${Object.entries(checks).map(([key,label])=>`<label><input type="checkbox" name="review-check" value="${key}">${label}</label>`).join('')}</div><label for="review-note">${tr('审核意见','Decision note')}</label><textarea id="review-note" maxlength="2000"></textarea><div class="actions"><button class="primary" data-decision="approve">${tr('通过并上榜','Approve & list')}</button><button class="text-button" data-decision="changes_requested">${tr('要求修改','Request changes')}</button><button class="danger text-button" data-decision="reject">${tr('拒绝','Reject')}</button></div>`;
  if(session.role==='maintainer'&&row.status==='approved') return `<label for="review-note">${tr('撤回原因','Withdrawal reason')}</label><textarea id="review-note" maxlength="2000"></textarea><button class="danger" data-decision="withdraw">${tr('撤回上榜结果','Withdraw listing')}</button>`;
  if(row.status==='changes_requested'&&session.role===row.owner) return `<h4>${tr('提交新修订','Submit a new revision')}</h4><div class="actions"><label class="upload">${tr('上传 JSON','Upload JSON')}<input id="resubmit-file" type="file" accept="application/json,.json" aria-label="Upload revised package"></label><button class="text-button" id="resubmit-sample">${tr('重新提交示例','Resubmit sample')}</button></div>`;
  if(row.status==='approved') return `<button class="text-button" data-view="community">${tr('查看社区结果','View community results')} →</button>`;
  return `<p class="muted">${row.status==='pending'?tr('材料已保存，等待维护者审核。','Package saved. Awaiting maintainer review.'):tr('此结果未上榜。','This result is not listed.')}</p>`;
}
function drawEvidence(index){
  const record=selected.bundle.evidence[index];
  const target=find('#event-visual');
  if(target)target.innerHTML=`<ol class="timeline" lang="en">${record.content.events.map(e=>`<li>${escape(e.kind.replaceAll('_',' '))}</li>`).join('')}</ol><div class="hash">SHA-256 ${record.sha256}</div><p class="small muted">${tr('模拟事件，未执行真实任务。','Synthetic events. No real task was executed.')}</p>`;
}
async function renderCommunity(){
  app.setAttribute('aria-busy','true');
  const data=await api('/api/leaderboard');
  if(view!=='community')return;
  app.innerHTML=data.entries.length?`<div class="table-wrap"><table><caption class="sr-only">${tr('本地模拟社区结果','Local synthetic community results')}</caption><thead><tr><th scope="col">${tr('代理 / 模型','Agent / model')}</th><th scope="col">DRS</th><th scope="col">${tr('任务成功率','Task success')}</th><th scope="col">${tr('审核','Review')}</th></tr></thead><tbody>${data.entries.map(row=>`<tr><td><h4>${escape(row.metadata.agent)}</h4><span class="muted small">${escape(row.metadata.model)}</span></td><td class="score">${row.metrics.drs}</td><td>${row.metrics.success}%</td><td>${status(row.status)} / r${row.revision}</td></tr>`).join('')}</tbody></table></div>`:`<div class="empty">${tr('暂无审核通过的结果。','No approved results yet.')}</div>`;
  app.setAttribute('aria-busy','false');
}
async function readFile(file){if(!file)throw new Error('Choose a JSON package.');if(file.size>2097152)throw new Error('Please use a file smaller than 2 MB.');return JSON.parse(await file.text());}
async function resubmit(value){selected=await api('/api/submissions',{bundle:value,id:selected.id,version:selected.version});await refresh();render();announce('新修订已提交，保留此前记录。','New revision submitted. Previous records are preserved.');}
async function action(event){
  const button=event.target.closest('button');if(!button||!root.contains(button)||identity.disabled)return;
  generation++;
  if(button.dataset.view){view=button.dataset.view;selected=null;tell('');await refresh();render();return;}
  button.disabled=true;
  try{
    if(button.dataset.open){selected=await api(`/api/submissions/${button.dataset.open}`);render();app.scrollIntoView({behavior:matchMedia('(prefers-reduced-motion: reduce)').matches?'instant':'smooth',block:'start'});}
    else if(button.id==='sample'){await prepare(await api('/api/demo-package'));}
    else if(button.id==='submit'){selected=await api('/api/submissions',{bundle});await refresh();bundle=null;validation=null;render();announce('已提交，审核通过后才会上榜。','Submitted. Review is required before listing.');}
    else if(button.id==='back'){selected=null;await refresh();render();}
    else if(button.dataset.decision){selected=await api(`/api/submissions/${selected.id}/review`,{version:selected.version,action:button.dataset.decision,checks:[...root.querySelectorAll('[name=review-check]:checked')].map(x=>x.value),note:find('#review-note').value});await refresh();render();announce('审核意见已保存。','Review decision saved.');}
    else if(button.id==='resubmit-sample'){await resubmit(await api('/api/demo-package'));}
    else if(button.id==='download'){const url=URL.createObjectURL(new Blob([JSON.stringify(selected.bundle,null,2)],{type:'application/json'}));const a=document.createElement('a');a.href=url;a.download=`submission-r${selected.revision}.json`;a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);}
  }finally{button.disabled=false;}
}
root.addEventListener('click',event=>{action(event).catch(report);});
root.addEventListener('change',async event=>{
  if(identity.disabled)return;
  if(event.target.id==='episode'){drawEvidence(Number(event.target.value));return;}
  if(event.target!==identity&&!['file','resubmit-file'].includes(event.target.id))return;
  generation++;
  const started=generation;
  const changingIdentity=event.target===identity;
  try{
    if(changingIdentity){
      identity.disabled=true;
      selected=null;bundle=null;validation=null;items=[];app.innerHTML='';
      app.setAttribute('aria-busy','true');
      session=await api('/api/session',{role:identity.value});
      view=session.role==='maintainer'?'review':'submit';tell('');await refresh();render();
    }
    else if(event.target.id==='file'){
      // A failed replacement upload must not leave an earlier package submit-ready.
      bundle=null;validation=null;
      find('.validation')?.remove();
      const value=await readFile(event.target.files[0]);
      if(started!==generation)throw new StaleOperation();
      await prepare(value);
    }
    else if(event.target.id==='resubmit-file'){
      const value=await readFile(event.target.files[0]);
      if(started!==generation)throw new StaleOperation();
      await resubmit(value);
    }
  }catch(error){if(started===generation){if(changingIdentity)render();report(error);}}
  finally{if(changingIdentity)identity.disabled=false;}
});
try{session=await api('/api/session');await refresh();render();identity.disabled=false;}catch(error){report(error);}
