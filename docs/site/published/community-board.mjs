const exact=(value,fields)=>value&&typeof value==='object'&&!Array.isArray(value)&&Object.keys(value).sort().join('|')===fields.slice().sort().join('|');
const login=value=>typeof value==='string'&&/^[A-Za-z0-9][A-Za-z0-9-]{0,38}$/.test(value);
const safe=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
export function communityMarkup(board,language='en'){
  if(!exact(board,['schema','entries'])||!Array.isArray(board.entries)||board.entries.length>10000)throw Error('Invalid community snapshot');
  const legacy=board.schema==='async-rbench-community-board-1';
  if(board.schema!=='async-rbench-community-board-2'&&!legacy)throw Error('Unsupported community snapshot');
  const ids=new Set();
  for(const r of board.entries){
    const fields=['metadata','metrics','submitter','reviewer','reviewed_at','verification','score_policy_version'];
    if(!exact(r,fields.concat(legacy?['issue','url','receipt_sha256','review_url']:['id'])))throw Error('Invalid summary');
    if(legacy){
      const issueURL=`https://github.com/pope8zdt/Async-RBench/issues/${r.issue}`;
      if(!Number.isSafeInteger(r.issue)||r.issue<=0||r.url!==issueURL||typeof r.review_url!=='string'||!r.review_url.startsWith(issueURL+'#issuecomment-')||!/^[1-9][0-9]*$/.test(r.review_url.slice((issueURL+'#issuecomment-').length))||typeof r.receipt_sha256!=='string'||!/^[0-9a-f]{64}$/.test(r.receipt_sha256))throw Error('Invalid legacy summary');
    }else if(typeof r.id!=='string'||!/^[0-9a-f]{32}$/.test(r.id))throw Error('Invalid summary');
    const id=legacy?r.issue:r.id;if(ids.has(id))throw Error('Duplicate summary');ids.add(id);
    if(!exact(r.metadata,['agent','model','organization','code_revision'])||!['agent','model','organization'].every(k=>typeof r.metadata[k]==='string'&&/^[\p{L}\p{N}_.:/() -]{1,100}$/u.test(r.metadata[k])&&r.metadata[k].trim())||typeof r.metadata.code_revision!=='string'||!/^[0-9a-f]{40}$/.test(r.metadata.code_revision))throw Error('Invalid metadata');
    if(!exact(r.metrics,['drs','success','tasks','episodes','repetitions'])||!['tasks','episodes','repetitions'].every(k=>Number.isSafeInteger(r.metrics[k])&&r.metrics[k]>0)||r.metrics.episodes!==r.metrics.tasks*r.metrics.repetitions||(!legacy&&(r.metrics.tasks!==200||r.metrics.episodes!==600||r.metrics.repetitions!==3))||!['drs','success'].every(k=>typeof r.metrics[k]==='number'&&Number.isFinite(r.metrics[k])&&r.metrics[k]>=0&&r.metrics[k]<=100))throw Error('Invalid metrics');
    if(!login(r.submitter)||!login(r.reviewer)||r.submitter.toLowerCase()===r.reviewer.toLowerCase()||r.verification!=='maintainer-reviewed'||r.score_policy_version!=='async-rbench-runtime-boundaries-1'||typeof r.reviewed_at!=='string'||!/^\d{4}-\d\d-\d\dT.*(?:Z|[+-]\d\d:\d\d)$/.test(r.reviewed_at)||!Number.isFinite(Date.parse(r.reviewed_at)))throw Error('Invalid review');
  }
  const zh=language==='zh';
  if(!board.entries.length)return `<p class="repository-empty">${zh?'暂无已审核的社区结果。':'No reviewed community results yet.'}</p>`;
  return `<div class="table-scroll"><table><caption>${zh?'社区结果':'Community results'}</caption><thead><tr><th scope="col">${zh?'智能体 / 模型':'Agent / model'}</th><th scope="col">${zh?'提交者':'Submitter'}</th><th scope="col">DRS</th><th scope="col">S · Async %</th><th scope="col">${zh?'任务 × 重复':'Tasks × repetitions'}</th></tr></thead><tbody>${board.entries.slice().sort((a,b)=>b.metrics.drs-a.metrics.drs||String(a.id??a.issue).localeCompare(String(b.id??b.issue))).map(r=>`<tr><th scope="row">${safe(r.metadata.agent)} / ${safe(r.metadata.model)}</th><td>${safe(r.submitter)}</td><td>${r.metrics.drs.toFixed(1)}</td><td>${r.metrics.success.toFixed(1)}</td><td>${r.metrics.tasks} × ${r.metrics.repetitions}</td></tr>`).join('')}</tbody></table></div>`;
}
