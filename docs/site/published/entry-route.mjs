export function legacyDestination(href) {
  const url = new URL(href);
  if(url.pathname !== '/' && url.pathname !== '/index.html') return null;
  if(!url.hash && !url.searchParams.has('case')) return null;
  return '/benchmark/' + url.search + url.hash;
}

if(typeof document !== 'undefined') {
  const destination = legacyDestination(location.href);
  if(destination) location.replace(destination);
}
