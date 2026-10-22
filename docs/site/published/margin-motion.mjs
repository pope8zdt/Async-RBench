export const canMove = ({hidden,reduced,paused}) => !hidden && !reduced && !paused;
export const motionLabel = (paused,language) => language==='zh'
  ? (paused?'继续背景':'暂停背景') : (paused?'Resume background':'Pause background');

function mount(){
  const backdrop=document.querySelector('.margin-motion');
  if(!backdrop)return;
  const media=matchMedia('(prefers-reduced-motion: reduce)');
  let paused=false;
  try{paused=sessionStorage.getItem('margin-motion-paused')==='true';}catch{}
  const control=document.querySelector('[data-submission-guide]')?null:document.createElement('button');
  if(control){
    control.type='button';control.className='margin-motion-control';
    document.querySelector('footer')?.append(control);
  }
  function update(){
    backdrop.dataset.moving=String(canMove({hidden:document.hidden,reduced:media.matches,paused}));
    if(control){
      control.textContent=motionLabel(paused,document.documentElement.lang);
      control.setAttribute('aria-pressed',String(paused));
      control.hidden=media.matches;
    }
  }
  control?.addEventListener('click',()=>{
    paused=!paused;
    try{sessionStorage.setItem('margin-motion-paused',String(paused));}catch{}
    update();
  });
  document.addEventListener('visibilitychange',update);
  media.addEventListener('change',update);
  new MutationObserver(update).observe(document.documentElement,{attributes:true,attributeFilter:['lang']});
  update();
}
if(typeof document!=='undefined')mount();
