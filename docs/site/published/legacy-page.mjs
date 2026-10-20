const link=document.querySelector('[data-destination]');
if(link){const target=new URL(link.href,location.href),source=new URL(location.href);if(target.pathname.endsWith('/tasks/')){for(const name of ['case','seq'])if(source.searchParams.has(name))target.searchParams.set(name,source.searchParams.get(name));}location.replace(target.href);}
