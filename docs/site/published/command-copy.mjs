export async function copyCommand(text,clipboard){
  if(!clipboard?.writeText)return false;
  try{await clipboard.writeText(text);return true;}catch{return false;}
}

export function enhanceCommands(root){
  const english=()=>document.documentElement.lang==='en';
  const labels=[];
  for(const pre of root.querySelectorAll('pre')){
    if(pre.closest('.command-block'))continue;
    const wrapper=document.createElement('div');wrapper.className='command-block';
    const copy=document.createElement('button');copy.type='button';copy.className='command-copy';
    const status=document.createElement('span');status.className='sr-only';status.setAttribute('role','status');
    let timer;
    const label=()=>{copy.textContent=english()?'Copy':'复制';copy.setAttribute('aria-label',english()?'Copy code':'复制代码');};
    pre.replaceWith(wrapper);wrapper.append(pre,copy,status);label();labels.push(label);
    copy.addEventListener('click',async()=>{
      clearTimeout(timer);
      const ok=await copyCommand(pre.textContent,navigator.clipboard);
      copy.textContent=ok?(english()?'Copied':'已复制'):(english()?'Select to copy':'请选中复制');
      status.textContent=ok?(english()?'Code copied.':'代码已复制。'):(english()?'Clipboard unavailable. Select the code to copy it manually.':'无法访问剪贴板，请选中代码手动复制。');
      timer=setTimeout(()=>{label();status.textContent='';},2400);
    });
  }
  document.addEventListener('site-language-change',()=>labels.forEach(label=>label()));
}
