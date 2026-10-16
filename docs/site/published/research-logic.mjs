export function pageWindow(total, requestedPage=1, pageSize=6) {
  const count=Math.max(0,Math.trunc(Number(total)||0));
  const size=Number.isFinite(pageSize)&&pageSize>0?Math.trunc(pageSize):6;
  const pages=Math.max(1,Math.ceil(count/size));
  const page=Math.max(1,Math.min(pages,Math.trunc(Number(requestedPage)||1)));
  return {page,pages,start:(page-1)*size,end:Math.min(page*size,count)};
}

export function activeSection(sections, headerHeight) {
  if(!sections.length)return null;
  const threshold=Math.max(0,headerHeight)+100;
  let active=sections[0].id;
  for(const section of sections)if(section.top<=threshold)active=section.id;
  return active;
}

export function sameFilters(a,b) {
  return ['query','source','difficulty'].every(key=>(a?.[key]||'')===(b?.[key]||''));
}

export function initialAnchor(initialHash,currentHash,interrupted,search=''){
  if(interrupted||initialHash!==currentHash)return null;
  if((!initialHash||initialHash==='#trajectories')&&['release','replay','early-stop','reconsider','defer','continue'].includes(new URLSearchParams(search).get('case')))return 'trace-explorer';
  if(!initialHash)return null;
  try{return decodeURIComponent(initialHash.slice(1))||null;}catch{return null;}
}
