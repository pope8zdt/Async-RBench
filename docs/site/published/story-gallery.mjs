export const selectedStage = value => Number.isInteger(Number(value)) && Number(value)>=0 && Number(value)<3 ? Number(value) : 0;
export const requestsExplorer = href => {const url=new URL(href);return (!url.hash||url.hash==='#trajectories')&&['release','replay','early-stop','reconsider','defer','continue'].includes(url.searchParams.get('case'));};
export function revealExplorer(explorer,reducedMotion=false){
  if(!explorer)return;
  explorer.open=true;
  explorer.scrollIntoView({block:'start',behavior:reducedMotion?'instant':'smooth'});
}

function mount() {
  const data=document.getElementById('story-data');if(!data)return;
  const stories=JSON.parse(data.textContent);
  for(const article of document.querySelectorAll('.trace-story')) {
    const story=stories.find(item=>item.id===article.dataset.story);if(!story)continue;
    for(const button of article.querySelectorAll('[data-stage]'))button.addEventListener('click',()=>{
      const index=selectedStage(button.dataset.stage),event=story.events[index];
      for(const peer of article.querySelectorAll('[data-stage]'))peer.setAttribute('aria-pressed',String(peer===button));
      article.dataset.selected=String(index);
      article.querySelector('.story-event').textContent=JSON.stringify(event,null,2);
      article.querySelector('.story-seq').textContent='#'+event.seq;
    });
  }
  const explorer=document.getElementById('trace-explorer');
  const reveal=()=>{if(explorer&&requestsExplorer(location.href))revealExplorer(explorer,matchMedia('(prefers-reduced-motion: reduce)').matches);};
  addEventListener('popstate',reveal);addEventListener('hashchange',reveal);
  document.addEventListener('click',event=>{
    const link=event.target.closest('a[href]');
    if(!link||!explorer||event.defaultPrevented||event.button!==0||event.ctrlKey||event.metaKey||event.shiftKey||event.altKey)return;
    const url=new URL(link.href,location.href);
    if(url.origin!==location.origin||!requestsExplorer(url.href))return;
    explorer.open=true;
    if(url.pathname===location.pathname){
      event.preventDefault();history.pushState(history.state,'',url.pathname+url.search+url.hash);
      dispatchEvent(new PopStateEvent('popstate'));
      explorer.querySelector(`[data-case="${url.searchParams.get('case')}"]`)?.focus({preventScroll:true});
    }
  });
  reveal();
}
if(typeof document!=='undefined')mount();
