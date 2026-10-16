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
