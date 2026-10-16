export const ribbonMotion = (state={}) => Object.values(state).some(Boolean) ? 'paused' : 'running';

export function applyRibbonMotion({ribbon,viewport,track,toggle},state,language) {
  const browsing=!!(state.paused||state.focused||state.reduced);
  if(!browsing)viewport.scrollLeft=0;
  track.style.animationPlayState=ribbonMotion(state);
  ribbon.classList.toggle('browse-scenarios',browsing);
  toggle.setAttribute('aria-pressed',String(!!state.paused));
  toggle.textContent=state.paused?'▶':'Ⅱ';
  toggle.setAttribute('aria-label',language==='zh'?(state.paused?'继续场景滚动':'暂停场景滚动'):(state.paused?'Resume scenario scroll':'Pause scenario scroll'));
}

function mount() {
  const ribbon=document.querySelector('.scenario-ribbon');if(!ribbon)return;
  const viewport=ribbon.querySelector('.scenario-window'),track=ribbon.querySelector('.scenario-track'),toggle=ribbon.querySelector('#scenario-motion');
  const reduced=matchMedia('(prefers-reduced-motion: reduce)');
  const state={paused:false,hovered:false,focused:false,detail:false,hidden:document.hidden,reduced:reduced.matches};
  const update=()=>applyRibbonMotion({ribbon,viewport,track,toggle},state,document.documentElement.lang);
  const resize=()=>{ribbon.style.setProperty('--ribbon-distance',Math.min(0,viewport.clientWidth-track.scrollWidth)+'px');};
  new ResizeObserver(resize).observe(viewport);new ResizeObserver(resize).observe(track);
  ribbon.classList.add('ribbon-ready');
  ribbon.addEventListener('pointerenter',()=>{state.hovered=true;update();});
  ribbon.addEventListener('pointerleave',()=>{state.hovered=false;update();});
  const focus=()=>{state.focused=ribbon.contains(document.activeElement)&&document.activeElement.matches(':focus-visible');update();};
  ribbon.addEventListener('focusin',focus);
  ribbon.addEventListener('focusout',()=>queueMicrotask(focus));
  toggle.addEventListener('click',()=>{state.paused=!state.paused;update();});
  reduced.addEventListener('change',()=>{state.reduced=reduced.matches;update();});
  document.addEventListener('visibilitychange',()=>{state.hidden=document.hidden;update();});
  document.addEventListener('site-language-change',()=>{update();resize();});
  if(typeof HTMLElement.prototype.showPopover==='function') for(const item of track.children) {
    const button=item.querySelector('button'),panel=item.querySelector('.scenario-note');let pinned=false,timer;
    const close=()=>{if(panel.matches(':popover-open'))panel.hidePopover();button.setAttribute('aria-expanded','false');state.detail=!!ribbon.querySelector('.scenario-note:popover-open');update();};
    const open=()=>{clearTimeout(timer);if(!panel.matches(':popover-open'))panel.showPopover();state.detail=true;update();const r=button.getBoundingClientRect();panel.style.left=Math.max(12,Math.min(r.left,innerWidth-panel.offsetWidth-12))+'px';panel.style.top=Math.min(r.bottom+8,innerHeight-panel.offsetHeight-12)+'px';button.setAttribute('aria-expanded','true');};
    button.addEventListener('pointerenter',event=>{if(event.pointerType==='mouse')open();});
    button.addEventListener('pointerleave',()=>{timer=setTimeout(()=>{if(!pinned&&!(document.activeElement===button&&button.matches(':focus-visible')))close();},150);});
    button.addEventListener('focus',()=>{focus();open();});
    button.addEventListener('blur',()=>{pinned=false;close();});
    button.addEventListener('click',()=>{pinned=!pinned;pinned?open():close();});
    button.addEventListener('keydown',event=>{if(event.key==='Escape'){pinned=false;close();event.preventDefault();}});
    panel.addEventListener('pointerenter',()=>clearTimeout(timer));panel.addEventListener('pointerleave',()=>{if(!pinned)close();});
    document.addEventListener('click',event=>{if(!item.contains(event.target)){pinned=false;close();}});
    document.addEventListener('scroll',close,{capture:true,passive:true});
    document.addEventListener('site-language-change',close);
  }
  resize();update();
}
if(typeof document!=='undefined')mount();
