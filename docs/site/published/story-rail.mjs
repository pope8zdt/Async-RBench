export const railIsPaused = state => Object.values(state).some(Boolean);
export const railInView = (top,bottom,height) => bottom>0 && top<height;

export function pageRail(position, direction, step) {
  if (step <= 0) return {rotate:0,position:0,target:0};
  let rotate=Math.floor(position/step), offset=position-rotate*step;
  if(direction<0 && offset<1) {rotate--;offset+=step;}
  return {rotate,position:offset,target:direction>0?step:0};
}

export function advanceRail(position, step, elapsed) {
  if (step <= 0) return {position:0,rotate:0};
  const next=Math.max(0,position)+24*Math.max(0,Math.min(elapsed,100))/1000;
  const rotate=Math.floor(next/step);
  return {position:next-rotate*step,rotate};
}

function mountRail(rail) {
  const viewport = rail.querySelector('.story-window');
  const gallery = rail.querySelector('.story-gallery');
  const toggle = rail.querySelector('[data-story-motion]');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const state = {paused:false, hovered:false, focused:false, detail:false,
    hidden:document.hidden, offscreen:true, reduced:reduced.matches};
  let lastTime=0, position=viewport.scrollLeft, step=0;
  const measure=()=>{step=gallery.firstElementChild.getBoundingClientRect().width+(parseFloat(getComputedStyle(gallery).columnGap)||0);};
  new ResizeObserver(measure).observe(viewport);
  measure();
  // Recycle the original nodes at the invisible left edge. Their IDs, open
  // records and event listeners stay intact; there are no duplicate stories.
  const rotate=count=>{
    for(let i=0;i<Math.abs(count)%gallery.children.length;i++) {
      if(count>0)gallery.append(gallery.firstElementChild);
      else gallery.prepend(gallery.lastElementChild);
    }
  };
  const update = () => {
    const zh = document.documentElement.lang === 'zh';
    rail.dataset.motion = railIsPaused(state) ? 'paused' : 'running';
    rail.dataset.pauseReasons=Object.keys(state).filter(key=>state[key]).join(' ');
    toggle.setAttribute('aria-pressed', String(state.paused));
    toggle.setAttribute('aria-label', state.paused ? (zh?'继续轨迹滚动':'Resume trajectory scroll') : (zh?'暂停轨迹滚动':'Pause trajectory scroll'));
    toggle.textContent = state.paused ? '▷' : 'Ⅱ';
    rail.querySelector('[data-story-direction="-1"]').setAttribute('aria-label',zh?'上一组轨迹':'Previous trajectories');
    rail.querySelector('[data-story-direction="1"]').setAttribute('aria-label',zh?'下一组轨迹':'Next trajectories');
    viewport.setAttribute('aria-label',zh?'真实轨迹，横向浏览':'Recorded trajectories, scroll horizontally');
  };
  const set = (key, value) => {state[key] = value; update();};
  toggle.addEventListener('click', () => set('paused', !state.paused));
  rail.addEventListener('pointerenter', e => {if(e.pointerType==='mouse')set('hovered',true);});
  rail.addEventListener('pointerleave', () => set('hovered',false));
  rail.addEventListener('focusin', e => {if(e.target.matches(':focus-visible'))set('focused',true);});
  rail.addEventListener('focusout', e => {if(!rail.contains(e.relatedTarget))set('focused',false);});
  viewport.addEventListener('pointerdown', e => {if(e.pointerType!=='mouse')set('paused',true);});
  viewport.addEventListener('wheel', e => {if(Math.abs(e.deltaX)>0||e.shiftKey)set('paused',true);},{passive:true});
  viewport.addEventListener('scroll', () => {position=viewport.scrollLeft;},{passive:true});
  for(const button of rail.querySelectorAll('[data-story-direction]'))button.addEventListener('click', () => {
    set('paused',true);
    measure();
    const page=pageRail(viewport.scrollLeft,Number(button.dataset.storyDirection),step);
    rotate(page.rotate);
    position=page.position;
    viewport.scrollLeft=position;
    viewport.scrollTo({left:page.target,behavior:state.reduced?'instant':'smooth'});
  });
  for(const detail of rail.querySelectorAll('details'))detail.addEventListener('toggle', () => set('detail',!!rail.querySelector('details[open]')));
  document.addEventListener('visibilitychange', () => set('hidden',document.hidden));
  document.addEventListener('site-language-change', update);
  reduced.addEventListener('change', () => set('reduced',reduced.matches));
  const checkVisibility=()=>{
    const rect=rail.getBoundingClientRect();
    const offscreen=!railInView(rect.top,rect.bottom,innerHeight);
    if(state.offscreen!==offscreen)set('offscreen',offscreen);
  };
  const observer=new IntersectionObserver(checkVisibility);
  observer.observe(rail);
  // Anchor restoration and an embedded browser can deliver visibility updates
  // in different orders. Recheck on actual scrolling, not just observer entries.
  addEventListener('scroll',checkVisibility,{passive:true});
  addEventListener('resize',checkVisibility);
  addEventListener('pageshow',checkVisibility);
  const frame = time => {
    if(!railIsPaused(state)) {
      const next=advanceRail(position,step,time-lastTime);
      rotate(next.rotate);
      position=next.position;viewport.scrollLeft=position;
    }
    lastTime=time;requestAnimationFrame(frame);
  };
  checkVisibility();update();requestAnimationFrame(frame);
}
if(typeof document!=='undefined')document.querySelectorAll('.story-rail').forEach(mountRail);
