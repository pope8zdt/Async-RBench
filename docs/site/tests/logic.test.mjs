import test from 'node:test';
import assert from 'node:assert/strict';

const load = () => import('../logic.mjs');

test('ranking orders numeric scores, leaves missing scores unranked, and does not mutate input', async () => {
  const { rankResults } = await load();
  const rows = [{ id: 'missing', drs: null }, { id: 'low', drs: 19.2 }, { id: 'high', drs: 45.1 }];
  assert.deepEqual(rankResults(rows, 'drs').map(r => [r.id, r.rank]), [['high', 1], ['low', 2], ['missing', null]]);
  assert.deepEqual(rows.map(r => r.id), ['missing', 'low', 'high']);
});

test('ties share a rank and paper deltas are used without recomputing rounded rates', async () => {
  const { rankResults } = await load();
  const rows = [{ id: 'sonnet', delta: -4.2, batched: 42.3, async: 38.2 }, { id: 'terra', delta: -2.5 }, { id: 'tie', delta: -2.5 }];
  assert.deepEqual(rankResults(rows, 'delta').map(r => r.rank), [1, 1, 3]);
  assert.equal(rankResults(rows, 'delta').at(-1).delta, -4.2);
});

test('search filters already-ranked records so displayed ranks remain global', async () => {
  const { rankResults, filterResults } = await load();
  const ranked = rankResults([{ id: 's', model: 'Sonnet', drs: 45.1 }, { id: 't', model: 'Terra', drs: 39.7 }], 'drs');
  assert.deepEqual(filterResults(ranked, ' TERRA ').map(r => r.rank), [2]);
  assert.equal(filterResults(ranked, 'absent').length, 0);
});

test('task filters combine source, difficulty and case-insensitive title or id search', async () => {
  const { filterTasks } = await load();
  const tasks = [{ id: 'case-a', title: 'Merge files', source: 'gaia2', difficulty: 'hard' }, { id: 'case-b', title: 'Merge files', source: 'osworld', difficulty: 'medium' }];
  assert.deepEqual(filterTasks(tasks, { query: ' MERGE ', source: 'gaia2', difficulty: 'hard' }).map(t => t.id), ['case-a']);
  assert.equal(filterTasks(tasks, { query: 'case-b', source: 'gaia2' }).length, 0);
  assert.equal(filterTasks(tasks, {}).length, 2);
});

test('scenario sorting uses the selected mean while preserving its uncertainty', async () => {
  const { rankResults } = await load();
  const rows = [
    { id: 'a', drs: 45.1, scenarios: { replay: { mean: 15.5, sd: 1.2 } } },
    { id: 'b', drs: 39.7, scenarios: { replay: { mean: 18.5, sd: 1.6 } } },
    { id: 'missing', scenarios: {} },
  ];
  const ranked = rankResults(rows, 'replay');
  assert.deepEqual(ranked.map(r => [r.id, r.rank]), [['b', 1], ['a', 2], ['missing', null]]);
  assert.equal(ranked[0].scenarios.replay.sd, 1.6);
  assert.deepEqual(rows.map(r => r.id), ['a', 'b', 'missing']);
});

test('agent search accepts the model abbreviation printed in the paper table', async () => {
  const { filterResults } = await load();
  const rows = [{ id: 'gemini', model: 'Gemini 3 Flash High', paper_label: 'Gemini 3 Flash-H' }];
  assert.equal(filterResults(rows, 'Gemini 3 Flash-H').length, 1);
  assert.equal(filterResults(rows, 'Flash High').length, 1);
});
