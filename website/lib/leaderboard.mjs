export function coverageStatus(record) {
  return record.coverageStatus !== 'incomplete' &&
    record.pairedComplete === true &&
    record.caseCount > 0 &&
    record.completedCases === record.caseCount
    ? 'complete'
    : 'incomplete';
}

export function executionStatus(record) {
  return ['running', 'completed', 'failed', 'stopped'].includes(
    record.executionStatus,
  )
    ? record.executionStatus
    : 'unknown';
}

export function reviewStatus(record) {
  return ['materials_reviewed', 'independently_reproduced'].includes(
    record.reviewStatus,
  )
    ? record.reviewStatus
    : 'self_reported';
}

export function metricValue(record, metric) {
  if (metric === 'delta') {
    const linear = metricValue(record, 'linear');
    const async = metricValue(record, 'async');
    // Remove subtraction noise so mathematically equal differences tie.
    return linear === null || async === null
      ? null
      : Number((linear - async).toFixed(12));
  }
  const observed = {
    linear: 'observedLinear',
    async: 'observedAsync',
    drs: 'observedDrs',
  };
  const value =
    coverageStatus(record) === 'complete'
      ? record[metric]
      : record[observed[metric]];
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}

export function leaderboardRows(records, metric, query = '') {
  const rows = records
    .map((record) => {
      const value = metricValue(record, metric);
      const complete = coverageStatus(record) === 'complete';
      const eligible =
        complete && reviewStatus(record) !== 'self_reported' && value !== null;
      return {
        record,
        value,
        complete,
        rank: null,
        group: eligible ? 0 : complete ? 1 : 2,
      };
    })
    .sort(
      (a, b) =>
        a.group - b.group ||
        (a.value === null
          ? b.value === null
            ? 0
            : 1
          : b.value === null
            ? -1
            : b.value - a.value) ||
        a.record.id.localeCompare(b.record.id),
    );
  let position = 0;
  let previousValue;
  let previousRank = 0;
  for (const row of rows) {
    if (row.group !== 0) continue;
    position += 1;
    row.rank = row.value === previousValue ? previousRank : position;
    previousValue = row.value;
    previousRank = row.rank;
  }
  const search = query.trim().toLowerCase();
  return rows.filter(({ record }) =>
    `${record.model} ${record.id}`.toLowerCase().includes(search),
  );
}
