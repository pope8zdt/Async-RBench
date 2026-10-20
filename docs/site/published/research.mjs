import {communityMarkup} from './community-board.mjs';
export {communityMarkup};
export function tabIndex(key,index,length){return ({ArrowRight:(index+1)%length,ArrowLeft:(index+length-1)%length,Home:0,End:length-1})[key]??null;}
export async function copyCitation(text,write){try{await write(text);return true;}catch{return false;}}
export function sectionAt(sections,offset){return sections.filter(section=>section.top<=offset).at(-1)?.id??null;}
export function legacyResearchDestination(href){
  const u=new URL(href);
  if(u.hash==='#trajectories'||u.searchParams.has('case'))return u.pathname.replace(/benchmark(?:\/index\.html|\/)?$/,'tasks/')+u.search+'#records';
  if(['#guide','#installing','#configuring','#running','#reading-results'].includes(u.hash))return 'https://github.com/pope8zdt/Async-RBench#quick-start';
  return null;
}

function mount(){
  const root=document.documentElement,lang=()=>root.lang==='zh'?'zh':'en',tr=(en,zh)=>lang()==='zh'?zh:en;
  if(document.body.hasAttribute('data-editorial-home')){const to=legacyResearchDestination(location.href);if(to){location.replace(to);return;}}
  const language=document.getElementById('language'),theme=document.getElementById('theme');
  function labels(){
    document.querySelectorAll('[data-en][data-zh]').forEach(n=>{n.textContent=n.dataset[lang()];});
    language.textContent=tr('中文','English');language.setAttribute('aria-label',tr('切换为中文','Switch to English'));
    theme.textContent=root.dataset.theme==='dark'?tr('Light','浅色'):tr('Dark','深色');
  }
  function save(){try{localStorage.setItem('async-rbench-paper-preferences',JSON.stringify({theme:root.dataset.theme}));}catch{}}
  language.hidden=theme.hidden=false;
  language.addEventListener('click',()=>{root.lang=lang()==='en'?'zh':'en';labels();document.dispatchEvent(new Event('site-language-change'));});
  theme.addEventListener('click',()=>{root.dataset.theme=root.dataset.theme==='dark'?'light':'dark';save();labels();});
  labels();root.classList.add('js-ready');
  const tabs=[...document.querySelectorAll('[role=tab]')];
  function select(index){tabs.forEach((tab,i)=>{tab.setAttribute('aria-selected',String(i===index));tab.tabIndex=i===index?0:-1;document.getElementById(tab.getAttribute('aria-controls')).hidden=i!==index;});}
  tabs.forEach((tab,i)=>{tab.addEventListener('click',()=>select(i));tab.addEventListener('keydown',event=>{const next=tabIndex(event.key,i,tabs.length);if(next===null)return;event.preventDefault();select(next);tabs[next].focus();});});
  if(tabs.length){document.querySelector('[role=tablist]').hidden=false;select(location.hash==='#community-panel'?1:0);window.addEventListener('hashchange',()=>{if(location.hash==='#community-panel')select(1);else if(location.hash==='#paper-panel')select(0);});}
  for(const button of document.querySelectorAll('[data-copy-target]')){
    button.hidden=false;button.addEventListener('click',async()=>{const pre=document.getElementById(button.dataset.copyTarget),status=document.querySelector('.copy-status');
      const success=await copyCitation(pre.textContent,text=>navigator.clipboard.writeText(text));
      if(!success){const selection=getSelection(),range=document.createRange();range.selectNodeContents(pre);selection.removeAllRanges();selection.addRange(range);pre.focus();}
      status.textContent=success?tr('BibTeX copied.','BibTeX 已复制。'):tr('Text selected. Press Ctrl+C (⌘C on Mac) to copy.','文本已选中，请按 Ctrl+C（Mac 使用 ⌘C）复制。');
    });
  }
  const community=document.querySelector('[data-community-board]');
  if(community){let board=null,state='loading';
    function draw(){community.innerHTML=board?communityMarkup(board,lang()):`<p>${state==='loading'?tr('Loading community results…','正在载入社区结果…'):tr('Community results could not be loaded. Please reload the page.','社区结果无法载入，请刷新页面重试。')}</p>`;}
    document.addEventListener('site-language-change',draw);draw();
    fetch(community.dataset.communityUrl,{credentials:'omit',cache:'no-store'}).then(async response=>{if(!response.ok)throw Error();const result=await response.json();communityMarkup(result);board=result;draw();}).catch(()=>{state='error';board=null;draw();});
  }
  const links=[...document.querySelectorAll('header nav a[href^="#"]')];
  const sections=[...document.querySelectorAll('main>section[id]')];let scrollFrame=0;
  function highlight(){scrollFrame=0;const id=sectionAt(sections.map(section=>({id:section.id,top:section.getBoundingClientRect().top})),document.querySelector('header').offsetHeight+60);links.forEach(link=>{if(link.hash==='#'+id)link.setAttribute('aria-current','location');else link.removeAttribute('aria-current');});}
  function queueHighlight(){if(!scrollFrame)scrollFrame=requestAnimationFrame(highlight);}
  window.addEventListener('scroll',queueHighlight,{passive:true});window.addEventListener('resize',queueHighlight);document.addEventListener('site-language-change',queueHighlight);highlight();
}
if(typeof document!=='undefined')mount();
