import test from 'node:test';
import assert from 'node:assert/strict';

import {
  TRACK_B_FRAMEWORKS,
  buildTrackBConfig,
  buildTrackBCommands,
} from '../lib/track-b.mjs';


test('Track B exposes three maintained frameworks', () => {
  assert.deepEqual(
    TRACK_B_FRAMEWORKS.map(({ id }) => id),
    ['claude-code', 'langgraph', 'openai-agents'],
  );
});


test('Track B builder emits a runnable local config and command', () => {
  const config = buildTrackBConfig({
    framework: 'openai-agents',
    model: 'gpt-test',
    credentialEnv: 'OPENAI_API_KEY',
    component: 'default',
  });
  const commands = buildTrackBCommands('track-b-config.yaml', 'gpt-test');

  assert.match(config, /^track: B$/m);
  assert.match(config, /^framework: openai-agents$/m);
  assert.match(config, /^model: gpt-test$/m);
  assert.match(commands, /python -m async_rbench\.track_b doctor/);
  assert.match(commands, /python -m async_rbench\.track_b run/);
  assert.match(commands, /--model "gpt-test"/);
  assert.doesNotMatch(commands, /simulate/i);
});


test('custom harness selection emits a module factory component', () => {
  const config = buildTrackBConfig({
    framework: 'claude-code',
    model: 'claude-test',
    credentialEnv: 'ANTHROPIC_API_KEY',
    component: 'context',
  });

  assert.match(config, /^components:$/m);
  assert.match(config, /context_builder: my_harness\.components:build_context/);
});
