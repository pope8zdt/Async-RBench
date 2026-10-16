// Pure playback functions. No task commands or scoring are executed here.
export function recordExcerpt(event) {
  const record = event.record;
  if (typeof record.command === 'string') return {kind:'command', text:record.command};
  if (typeof record.command_excerpt === 'string') return {kind:'excerpt', text:record.command_excerpt};
  const evidence = record.evidence && typeof record.evidence === 'object';
  const fields = evidence ? record.evidence : record;
  const text = Object.entries(fields).map(([key,value]) =>
    `${key}: ${typeof value === 'string' ? value : JSON.stringify(value)}`
  ).join('\n\n');
  return {kind:evidence ? 'evidence' : 'fields', text:text || '{}'};
}
export function displayedEvents(trajectory, mode) {
  const keys = new Set(trajectory.milestones.map(m => m.seq));
  return trajectory.events.filter(e => mode === 'all' || keys.has(e.seq));
}
export const stepIndex = (index, direction, count) => Math.max(0, Math.min(count - 1, index + direction));
export const eventPosition = (event, duration) => duration > 0 ? Math.max(0, Math.min(100, event.elapsed_ms / duration * 100)) : 0;
export function laneState(events, lane, seq) {
  let state = 'pending';
  for (const e of events) {
    if (e.seq > seq) break;
    if (e.lane !== lane) continue;
    if (e.type === 'child_started') state = 'running';
    if (e.type === 'child_completed') state = 'completed';
    if (e.type === 'child_cancelled') state = 'cancelled';
    if (e.type === 'child_failed') state = 'failed';
  }
  return state;
}
export function completionState(events, seq) {
  const records = new Map();
  for (const e of events) {
    if (e.seq > seq) break;
    const id = e.record.completion_id;
    if (!id) continue;
    if (!records.has(id)) records.set(id, {id, presentations:0, decision:null});
    const row = records.get(id);
    if (e.type === 'result_presented') row.presentations++;
    if (e.type === 'main_action' && e.record.kind === 'acknowledge_result') row.decision = e.record.decision;
  }
  return [...records.values()].filter(r => r.presentations || r.decision);
}
