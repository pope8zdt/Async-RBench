export function rankResults(records, metric = 'drs') {
  const rows = records.map(record => ({ ...record })).sort((a, b) => {
    const av = Number.isFinite(a[metric]) ? a[metric] : -Infinity;
    const bv = Number.isFinite(b[metric]) ? b[metric] : -Infinity;
    return bv - av || a.id.localeCompare(b.id);
  });
  let previous;
  let rank = null;
  return rows.map((row, index) => {
    const value = row[metric];
    if (!Number.isFinite(value)) return { ...row, rank: null };
    if (value !== previous) rank = index + 1;
    previous = value;
    return { ...row, rank };
  });
}

export function filterResults(records, query = '') {
  const term = query.trim().toLocaleLowerCase();
  return records.filter(row => `${row.id} ${row.model}`.toLocaleLowerCase().includes(term));
}

export function filterTasks(tasks, { query = '', source = '', difficulty = '' } = {}) {
  const term = query.trim().toLocaleLowerCase();
  return tasks.filter(task => (!source || task.source === source)
    && (!difficulty || task.difficulty === difficulty)
    && `${task.id} ${task.title}`.toLocaleLowerCase().includes(term));
}
