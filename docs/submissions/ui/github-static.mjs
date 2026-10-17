// The public file is a draft, never an approval. Private evidence stays offline.
const keys = (value, fields) => value && typeof value==='object' && !Array.isArray(value) && Object.keys(value).sort().join('|')===fields.sort().join('|');
export function preparePublicSubmission(value) {
  const fail = () => { throw new Error('invalid public submission'); };
  if (!keys(value,['schema','metadata','coverage','sha256']) || value.schema!=='async-rbench-public-submission-1' || !/^[a-f0-9]{64}$/.test(value.sha256)) fail();
  const meta=value.metadata, coverage=value.coverage;
  if (!keys(meta,['agent','model','organization','code_revision']) || !/^[a-f0-9]{40}$/.test(meta.code_revision)) fail();
  for (const key of ['agent','model','organization']) {
    if (typeof meta[key]!=='string' || !meta[key].trim() || !/^[\p{L}\p{N}_ .:/()-]{1,100}$/u.test(meta[key])) fail();
  }
  if (!keys(coverage,['tasks','episodes','repetitions'])) fail();
  for (const key of ['tasks','episodes','repetitions']) if (!Number.isSafeInteger(coverage[key]) || coverage[key]<=0) fail();
  if (coverage.episodes !== coverage.tasks*coverage.repetitions) fail();
  const body=`## Result submission\n\nAgent: ${meta.agent}\nModel: ${meta.model}\nOrganization: ${meta.organization}\nCode revision: ${meta.code_revision}\nTrack: Async\nCoverage: ${coverage.tasks} tasks, ${coverage.repetitions} repetitions\n\n<!-- async-rbench-receipt:${value.sha256} -->\nReceipt SHA-256: \`${value.sha256}\`\n\nPlease arrange private evidence review here. No private artifacts are attached.\nThis is a review request, not an approved benchmark result.`;
  const query=new URLSearchParams({title:`[Result submission] ${meta.agent}`,body});
  return {metadata:meta,coverage,sha256:value.sha256,body,url:`https://github.com/pope8zdt/Async-RBench/issues/new?${query}`};
}
