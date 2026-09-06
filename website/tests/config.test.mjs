import test from 'node:test';
import assert from 'node:assert/strict';
import { buildConfig, buildCommands } from '../lib/config-builder.mjs';
const valid = {
  model: 'exact-model',
  childModel: 'fixed-child',
  endpoint: 'https://example.com/v1/chat/completions',
  keyEnv: 'MODEL_API_KEY',
  childPool: 'fixed-pool',
};
test('configuration uses env references, paired canonical launcher and isolated workspace', () => {
  const yaml = buildConfig(valid);
  assert.match(yaml, /workspace_mode: container_clone/);
  assert.match(yaml, /api_key_env: "MODEL_API_KEY"/);
  assert.match(yaml, /child_pool_id: "fixed-pool"/);
  assert.match(buildCommands('formal', 3), /formal-61/);
  assert.match(buildCommands('formal', 3), /-Repetitions 3/);
});
test('reject unsafe environment names, missing model, embedded credentials and invalid repetitions', () => {
  assert.throws(() => buildConfig({ ...valid, keyEnv: 'x\nsecret' }));
  assert.throws(() => buildConfig({ ...valid, model: '' }));
  assert.throws(() =>
    buildConfig({ ...valid, endpoint: 'https://user:pass@example.com' }),
  );
  assert.throws(() => buildCommands('formal', 0));
});
test('model strings cannot inject YAML fields or PowerShell', () => {
  const yaml = buildConfig({ ...valid, model: 'x\nworkspace_mode: disabled' });
  assert.match(yaml, /main_model: "x\\nworkspace_mode: disabled"/);
  assert.equal(
    yaml.split('\n').filter((l) => l === 'workspace_mode: disabled').length,
    0,
  );
  assert.doesNotMatch(buildCommands('formal', 1), /x\nworkspace_mode/);
});
