const detailFields = [
  'seq',
  'actor',
  'child_id',
  'workstream_id',
  'elapsed_ms',
  'status',
  'reason',
  'result_id',
  'delivery_id',
];

const scoreFields = [
  'episode_id',
  'execution_mode',
  'score_status',
  'base_task_score',
  'async_drs',
];

export function parseTrace(text) {
  const events = [];
  for (const [index, raw] of String(text).split(/\r?\n/).entries()) {
    if (!raw.trim()) continue;
    let event;
    try {
      event = JSON.parse(raw);
    } catch {
      throw new Error(`Invalid trajectory JSONL at line ${index + 1}.`);
    }
    if (!event || typeof event !== 'object' || Array.isArray(event)) {
      throw new Error(`Invalid trajectory event at line ${index + 1}.`);
    }
    if (typeof event.type !== 'string' || !event.type) {
      throw new Error(`Trajectory event at line ${index + 1} has no type.`);
    }
    events.push(event);
    if (events.length > 5000) {
      throw new Error('Trajectory exceeds the 5,000 event viewer limit.');
    }
  }
  if (!events.length) throw new Error('Trajectory contains no events.');
  return events.sort(
    (left, right) => Number(left.seq ?? 0) - Number(right.seq ?? 0),
  );
}

export function eventDetails(event) {
  return Object.fromEntries(
    detailFields
      .filter((field) => event[field] !== undefined && event[field] !== null)
      .map((field) => [field, event[field]]),
  );
}

export function parseScore(text) {
  let score;
  try {
    score = JSON.parse(String(text));
  } catch {
    throw new Error('Invalid score JSON.');
  }
  if (!score || typeof score !== 'object' || Array.isArray(score)) {
    throw new Error('Score must be a JSON object.');
  }
  return Object.fromEntries(
    scoreFields
      .filter((field) => score[field] !== undefined && score[field] !== null)
      .map((field) => [field, score[field]]),
  );
}
