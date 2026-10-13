export function rankResults(records, metric = 'drs') {
  const score = record => record.scenarios?.[metric]?.mean ?? record[metric];
  const rows = records.map(record => ({ ...record })).sort((a, b) => {
    const av = Number.isFinite(score(a)) ? score(a) : -Infinity;
    const bv = Number.isFinite(score(b)) ? score(b) : -Infinity;
    return bv - av || a.id.localeCompare(b.id);
  });
  let previous;
  let rank = null;
  return rows.map((row, index) => {
    const value = score(row);
    if (!Number.isFinite(value)) return { ...row, rank: null };
    if (value !== previous) rank = index + 1;
    previous = value;
    return { ...row, rank };
  });
}

export function filterResults(records, query = '') {
  const term = query.trim().toLocaleLowerCase();
  return records.filter(row => `${row.id} ${row.model} ${row.paper_label || ''}`.toLocaleLowerCase().includes(term));
}

export function filterTasks(tasks, { query = '', source = '', difficulty = '' } = {}) {
  const term = query.trim().toLocaleLowerCase();
  return tasks.filter(task => (!source || task.source === source)
    && (!difficulty || task.difficulty === difficulty)
    && `${task.id} ${task.title}`.toLocaleLowerCase().includes(term));
}

const EVENT_FIELDS = ['seq', 'type', 'actor', 'child_id', 'workstream_id', 'elapsed_ms', 'status', 'reason', 'result_id', 'delivery_id'];

export function parseTrace(text, limit = 5000) {
  const events = [];
  for (const [index, raw] of text.split(/\r?\n/).entries()) {
    if (!raw.trim()) continue;
    if (events.length >= limit) throw new Error(`Trace exceeds ${limit} events`);
    try {
      const event = JSON.parse(raw);
      if (!event || Array.isArray(event) || typeof event !== 'object') throw new Error('object required');
      events.push(event);
    } catch {
      throw new Error(`Invalid JSONL at line ${index + 1}`);
    }
  }
  return events.sort((a, b) => (Number(a.seq) || 0) - (Number(b.seq) || 0));
}

function allowlist(source, fields) {
  return Object.fromEntries(fields.filter(key => source?.[key] !== undefined).map(key => [key, source[key]]));
}

export const publicEvent = event => allowlist(event, EVENT_FIELDS);
export function scoreSummary(score) {
  const first = (...keys) => keys.map(key => score?.[key]).find(value => value !== undefined);
  return Object.fromEntries(Object.entries({
    mode: first('mode', 'execution_mode'),
    drs: first('drs', 'async_drs', 'dynamic_replanning_score'),
    bts: first('bts', 'task_success', 'base_task_score'),
    status: first('status', 'episode_local_status', 'termination_reason'),
  }).filter(([, value]) => value !== undefined));
}
