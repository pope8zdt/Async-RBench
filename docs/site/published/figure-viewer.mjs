export const fitScale=(available,natural)=>Math.min(1,Math.max(1,available)/Math.max(1,natural));
export const stepScale=(scale,direction)=>Math.max(.1,Math.min(2,Math.round((scale+direction*.25)*100)/100));
export const centerAfterZoom=(scroll,viewport,before,after)=>Math.max(0,(before<=viewport?.5:(scroll+viewport/2)/before)*after-viewport/2);
export const isFigureLink=href=>/^\/(?:[A-Za-z0-9_-]+\/)*assets\/(getting-started|evaluation-overview)[^/]*\.svg$/.test(href.split(/[?#]/)[0]);

export function enhanceFigures(root){
  if(typeof HTMLDialogElement==='undefined'||!HTMLDialogElement.prototype.showModal)return;
  const links=[...root.querySelectorAll('a[href]')].filter(a=>isFigureLink(a.getAttribute('href')));
  if(!links.length)return;
  const el=(tag,cls,text)=>{const n=document.createElement(tag);if(cls)n.className=cls;if(text!==undefined)n.textContent=text;return n;};
  const dialog=el('dialog','figure-dialog'),toolbar=el('div','figure-toolbar'),heading=el('h2','',''),controls=el('div','figure-tools'),viewport=el('div','figure-viewport'),image=el('img');
  heading.id='figure-dialog-title';dialog.setAttribute('aria-labelledby',heading.id);
  viewport.tabIndex=0;viewport.setAttribute('role','region');image.alt='';image.draggable=false;viewport.append(image);
  const fit=el('button'),minus=el('button','','−'),plus=el('button','','+'),original=el('button','','1:1'),percent=el('output'),download=el('a','','SVG ↓'),close=el('button','figure-close','×');
  for(const b of [fit,minus,plus,original,close])b.type='button';
  download.setAttribute('download','');percent.setAttribute('aria-live','polite');
  controls.append(fit,minus,percent,plus,original,download,close);toolbar.append(heading,controls);dialog.append(toolbar,viewport);document.body.append(dialog);
  let scale=1,fitted=true,width=2100,height=1380,opener;
  const english=()=>document.documentElement.lang==='en';
  function labels(){
    heading.textContent=english()?'Evaluation framework':'评测框架';fit.textContent=english()?'Fit':'适应';
    minus.setAttribute('aria-label',english()?'Zoom out':'缩小');plus.setAttribute('aria-label',english()?'Zoom in':'放大');
    original.setAttribute('aria-label',english()?'Original size':'原尺寸');close.setAttribute('aria-label',english()?'Close figure':'关闭图示');
    viewport.setAttribute('aria-label',english()?'Scrollable figure':'可滚动查看的图示');
  }
  function zoom(next,keepCenter=true){
    const oldWidth=width*scale,oldHeight=height*scale,x=viewport.scrollLeft,y=viewport.scrollTop;
    scale=next;image.style.width=width*scale+'px';image.style.height=height*scale+'px';
    percent.textContent=Math.round(scale*100)+'%';minus.disabled=scale<=.1;plus.disabled=scale>=2;
    if(keepCenter){viewport.scrollLeft=centerAfterZoom(x,viewport.clientWidth,oldWidth,width*scale);viewport.scrollTop=centerAfterZoom(y,viewport.clientHeight,oldHeight,height*scale);}
  }
  function fitImage(){fitted=true;zoom(fitScale(viewport.clientWidth-32,width),false);viewport.scrollTo(0,0);}
  fit.addEventListener('click',fitImage);minus.addEventListener('click',()=>{fitted=false;zoom(stepScale(scale,-1));});plus.addEventListener('click',()=>{fitted=false;zoom(stepScale(scale,1));});original.addEventListener('click',()=>{fitted=false;zoom(1);});close.addEventListener('click',()=>dialog.close());
  dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close();});
  dialog.addEventListener('close',()=>{document.body.classList.remove('figure-open');opener?.focus({preventScroll:true});});
  addEventListener('resize',()=>{if(dialog.open&&fitted)fitImage();});
  for(const link of links)link.addEventListener('click',e=>{
    if(e.ctrlKey||e.metaKey||e.shiftKey||e.altKey||e.button!==0)return;
    e.preventDefault();opener=link;labels();const href=link.getAttribute('href');
    download.href=href;image.alt=link.querySelector('img')?.alt||(english()?'Async-RBench evaluation framework':'Async-RBench 评测框架');
    image.onload=()=>{width=image.naturalWidth||2100;height=image.naturalHeight||1380;fitImage();};
    image.src=href;dialog.showModal();document.body.classList.add('figure-open');fitImage();
  });
}
