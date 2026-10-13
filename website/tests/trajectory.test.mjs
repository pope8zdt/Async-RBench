import assert from 'node:assert/strict';
import test from 'node:test';
import { eventDetails, parseScore, parseTrace } from '../lib/trajectory.mjs';

test('trace parser accepts JSONL, orders events and ignores blank lines', () => {
  const trace = parseTrace(
    [
      JSON.stringify({
        seq: 3,
        type: 'result_delivered',
        actor: 'benchmark',
        elapsed_ms: 4200,
      }),
      '',
      JSON.stringify({
        seq: 1,
        type: 'episode_started',
        actor: 'benchmark',
        elapsed_ms: 0,
      }),
    ].join('\n'),
  );

  assert.deepEqual(
    trace.map((event) => event.seq),
    [1, 3],
  );
  assert.equal(trace[1].type, 'result_delivered');
});

test('trace parser identifies the invalid JSONL line without exposing its contents', () => {
  assert.throws(
    () => parseTrace('{"seq":1,"type":"ready"}\n{secret'),
    /line 2/i,
  );
});

test('event details expose useful replay fields and omit raw instructions', () => {
  const details = eventDetails({
    seq: 8,
    type: 'child_completed',
    actor: 'adapter',
    child_id: 'child-2',
    workstream_id: 'inspect',
    elapsed_ms: 1234,
    instruction: 'private task text',
    private_truth: { answer: 42 },
  });

  assert.deepEqual(details, {
    seq: 8,
    actor: 'adapter',
    child_id: 'child-2',
    workstream_id: 'inspect',
    elapsed_ms: 1234,
  });
});

test('score parser keeps only the public replay summary', () => {
  const score = parseScore(
    JSON.stringify({
      episode_id: 'demo-0-async',
      execution_mode: 'async',
      score_status: 'scored',
      base_task_score: 0.75,
      async_drs: 0.62,
      verifier_private_notes: ['hidden'],
    }),
  );

  assert.deepEqual(score, {
    episode_id: 'demo-0-async',
    execution_mode: 'async',
    score_status: 'scored',
    base_task_score: 0.75,
    async_drs: 0.62,
  });
});
