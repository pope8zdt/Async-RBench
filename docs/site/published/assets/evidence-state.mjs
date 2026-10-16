export const defaultEvents={release:289,replay:722,'early-stop':430,reconsider:684,defer:316,continue:505};
const points={release:[165,195,289,303,315,316],replay:[292,317,432,720,722,754,800],'early-stop':[265,300,368,428,430]};

export function keyEvents(c){
  const include=new Set([...c.milestones.map(m=>m.seq),...(points[c.id]||[])]);
  return c.events.filter(e=>include.has(e.seq));
}

export function readEvidenceLocation(href,cases){
  const params=new URL(href,'http://localhost').searchParams;
  const c=cases.find(c=>c.id===params.get('case'))||cases[0];
  const requested=Number(params.get('event'));
  const seq=params.has('event')&&c.events.some(e=>e.seq===requested)?requested:defaultEvents[c.id];
  const mode=params.get('records')==='all'||!keyEvents(c).some(e=>e.seq===seq)?'all':'key';
  return {caseId:c.id,seq,mode};
}

export function evidenceLocation(href,state,singlePage){
  const url=new URL(href,'http://localhost');
  url.searchParams.set('case',state.caseId);
  url.searchParams.set('event',state.seq);
  if(state.mode==='all')url.searchParams.set('records','all');else url.searchParams.delete('records');
  if(singlePage)url.hash='trajectories';
  return url.pathname+url.search+url.hash;
}
