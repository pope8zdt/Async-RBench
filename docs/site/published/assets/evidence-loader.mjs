export async function loadArchive(url, _hostname, fetcher) {
  const response = await fetcher(url);
  if (!response.ok) throw new Error('Records unavailable');
  const bundle = await response.json();
  const ids = ['release', 'replay', 'early-stop', 'reconsider', 'defer', 'continue'];
  if (bundle.publication !== 'reviewed-excerpts-v1' || bundle.local_only ||
      !Array.isArray(bundle.cases) || bundle.cases.length !== ids.length ||
      ids.some(id => !bundle.cases.some(c => c.id === id && Array.isArray(c.events) && c.events.length))) {
    throw new Error('Invalid public evidence archive');
  }
  return bundle;
}
