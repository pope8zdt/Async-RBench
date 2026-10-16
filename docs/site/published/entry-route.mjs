export const defaultLanguage = value => value === 'zh' ? 'zh' : 'en';

export function legacyDestination(href) {
  const url = new URL(href);
  if(url.pathname !== '/' && url.pathname !== '/index.html') return null;
  if(!url.hash && !url.searchParams.has('case')) return null;
  return '/benchmark/' + url.search + url.hash;
}

if(typeof document !== 'undefined') {
  let language;
  try { language = JSON.parse(localStorage.getItem('async-rbench-paper-preferences') || '{}').language; } catch {}
  document.documentElement.lang = defaultLanguage(language);
  const destination = legacyDestination(location.href);
  if(destination) location.replace(destination);
}
