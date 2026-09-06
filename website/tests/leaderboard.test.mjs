import test from 'node:test';
import assert from 'node:assert/strict';
import {
  coverageStatus,
  executionStatus,
  reviewStatus,
  metricValue,
  leaderboardRows,
} from '../lib/leaderboard.mjs';

const full = (id, values = {}) => ({
  id,
  model: id,
  caseCount: 47,
  completedCases: 47,
  pairedComplete: true,
  linear: 0.5,
  async: 0.4,
  drs: 0.3,
  reviewStatus: 'materials_reviewed',
  ...values,
});

test('coverage never infers execution or review and requires complete pairs', () => {
  assert.equal(coverageStatus(full('a')), 'complete');
  assert.equal(
    coverageStatus(
      full('a', { completedCases: 46, coverageStatus: 'complete' }),
    ),
    'incomplete',
  );
  assert.equal(
    coverageStatus(full('a', { pairedComplete: false })),
    'incomplete',
  );
  assert.equal(executionStatus({ completedCases: 46 }), 'unknown');
  assert.equal(executionStatus({ executionStatus: 'failed' }), 'failed');
  assert.equal(reviewStatus({ published: true }), 'self_reported');
});

test('missing scores stay missing while zero remains a real score', () => {
  assert.equal(
    metricValue(full('a', { drs: null, observedDrs: 0.9 }), 'drs'),
    null,
  );
  assert.equal(metricValue(full('a', { drs: 0 }), 'drs'), 0);
  assert.equal(
    metricValue(full('a', { pairedComplete: false, observedDrs: 0.2 }), 'drs'),
    0.2,
  );
  assert.equal(metricValue(full('a', { drs: NaN }), 'drs'), null);
});

test('selected metric sorts complete results separately from provisional results', () => {
  const records = [
    full('partial', {
      pairedComplete: false,
      completedCases: 1,
      observedLinear: 1,
    }),
    full('b', { linear: 0.9, async: 0.1 }),
    full('a', { linear: 0.2, async: 0.8 }),
  ];
  assert.deepEqual(
    leaderboardRows(records, 'linear').map((x) => x.record.id),
    ['b', 'a', 'partial'],
  );
  assert.deepEqual(
    leaderboardRows(records, 'async').map((x) => x.record.id),
    ['a', 'b', 'partial'],
  );
  assert.equal(leaderboardRows(records, 'linear')[2].rank, null);
});

test('formal ranks exclude unreviewed or missing results and use competition ties', () => {
  const rows = leaderboardRows(
    [
      full('self', { reviewStatus: undefined, drs: 1 }),
      full('a', { drs: 0.8 }),
      full('b', { drs: 0.8 }),
      full('c', { drs: 0.2 }),
      full('missing', { drs: null }),
    ],
    'drs',
  );
  assert.deepEqual(Object.fromEntries(rows.map((x) => [x.record.id, x.rank])), {
    a: 1,
    b: 1,
    c: 3,
    self: null,
    missing: null,
  });
});

test('search preserves global ranks and keeps distinct runs of one model', () => {
  const records = [
    full('one', { model: 'Same Model', drs: 0.1 }),
    full('two', { model: 'Same Model', drs: 0.2 }),
    full('top', { drs: 0.9 }),
  ];
  assert.deepEqual(
    leaderboardRows(records, 'drs', ' SAME ').map((x) => [x.record.id, x.rank]),
    [
      ['two', 2],
      ['one', 3],
    ],
  );
});
