const SCHEMA = 'async-rbench-community-board-2';
const POLICY = 'async-rbench-runtime-boundaries-1';
const keys = (o, names) => o && typeof o === 'object' && !Array.isArray(o) && Object.keys(o).sort().join('|') === names.slice().sort().join('|');
export const escapeHTML = value => String(value).replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const login = value => typeof value === 'string' && /^[A-Za-z0-9][A-Za-z0-9-]{0,38}$/.test(value);

function checkedBoard(board) {
  if (!keys(board,['schema','entries']) || board.schema!==SCHEMA || !Array.isArray(board.entries) || board.entries.length>10000) throw Error('Invalid community snapshot');
  const ids=new Set();
  for (const r of board.entries) {
    if (!keys(r,['id','metadata','metrics','submitter','reviewer','reviewed_at','verification','score_policy_version']) || !/^[0-9a-f]{32}$/.test(r.id) || ids.has(r.id)) throw Error('Invalid community summary');
    ids.add(r.id);
    const m=r.metadata, s=r.metrics;
    if (!keys(m,['agent','model','organization','code_revision']) || !['agent','model','organization'].every(k=>typeof m[k]==='string' && /^[\p{L}\p{N}_.:/() -]{1,100}$/u.test(m[k]) && m[k].trim()) || !/^[0-9a-f]{40}$/.test(m.code_revision)) throw Error('Invalid public metadata');
    if (!keys(s,['drs','success','tasks','episodes','repetitions']) || s.tasks!==200 || s.episodes!==600 || s.repetitions!==3 || !['drs','success'].every(k=>typeof s[k]==='number' && Number.isFinite(s[k]) && s[k]>=0 && s[k]<=100)) throw Error('Invalid public metrics');
    if (!login(r.submitter) || !login(r.reviewer) || r.submitter.toLowerCase()===r.reviewer.toLowerCase() || r.verification!=='maintainer-reviewed' || r.score_policy_version!==POLICY || typeof r.reviewed_at!=='string' || !/^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(r.reviewed_at) || !Number.isFinite(Date.parse(r.reviewed_at))) throw Error('Invalid review provenance');
  }
  return board;
}

export function submissionLinks(config) {
  if (!keys(config,['enabled','template','app']) || config.enabled!==true || typeof config.template!=='string' || !/^[A-Za-z0-9][A-Za-z0-9-]{0,38}\/[A-Za-z0-9][A-Za-z0-9._-]{0,99}$/.test(config.template) || typeof config.app!=='string' || !/^[a-z0-9][a-z0-9-]{0,99}$/.test(config.app)) return null;
  const [owner,name]=config.template.split('/');
  const query=new URLSearchParams({template_owner:owner,template_name:name,owner:'@me',visibility:'private'});
  return {create:`https://github.com/new?${query}`,install:`https://github.com/apps/${config.app}/installations/new`};
}

export function renderCommunity(board, lang='en') {
  checkedBoard(board);
  const zh=lang==='zh';
  if (!board.entries.length) return `<p class="repository-empty">${zh?'暂无已审核的社区提交。':'No reviewed submissions yet.'}</p>`;
  return `<div class="repository-table"><table><caption class="sr-only">${zh?'社区结果':'Community results'}</caption><thead><tr><th>${zh?'参评模型':'Agent / model'}</th><th>${zh?'提交者':'Submitted by'}</th><th>DRS</th><th>${zh?'成功率':'Task success'}</th></tr></thead><tbody>${board.entries.map(r=>`<tr><td><strong>${escapeHTML(r.metadata.agent)}</strong><span>${escapeHTML(r.metadata.model)}</span></td><td>${escapeHTML(r.submitter)}</td><td class="repository-score">${r.metrics.drs.toFixed(1)}</td><td class="repository-score">${r.metrics.success.toFixed(1)}%</td></tr>`).join('')}</tbody></table></div>`;
}

function mount(root) {
  const container=root.querySelector('[data-private-community]');
  let snapshot=null;
  const lang=()=>document.documentElement.lang==='zh'?'zh':'en';
  const draw=()=>{if(snapshot)container.innerHTML=renderCommunity(snapshot,lang());};
  const refresh=async()=>{
    try {
      const response=await fetch(root.dataset.communityUrl,{cache:'no-store',credentials:'omit'});
      if(!response.ok)throw Error();
      snapshot=checkedBoard(await response.json()); draw();
    } catch {snapshot=null;container.textContent=lang()==='zh'?'社区结果暂时无法加载。':'Community results are temporarily unavailable.';}
  };
  // Deployment supplies this public-only config separately, never OAuth secrets.
  let config={};
  try {config=JSON.parse(root.dataset.repositoryConfig||'{}');} catch {}
  const links=submissionLinks(config);
  if(links) {
    const button=root.querySelector('[data-create-private]');
    const anchor=document.createElement('a');
    anchor.className='repository-primary';anchor.href=links.create;anchor.rel='noopener noreferrer';
    anchor.innerHTML='<span class="i18n" lang="en">Create a private submission ↗</span><span class="i18n" lang="zh">创建私有提交 ↗</span>';
    button.replaceWith(anchor);
    const install=root.querySelector('[data-install-private]');install.href=links.install;install.rel='noopener noreferrer';install.hidden=false;
  }
  new MutationObserver(draw).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
  refresh();
  setInterval(()=>{if(document.visibilityState==='visible')refresh();},30000);
}
if(typeof document!=='undefined')document.querySelectorAll('[data-private-repository-root]').forEach(mount);
