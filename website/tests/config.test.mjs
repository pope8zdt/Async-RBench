import test from 'node:test';
import assert from 'node:assert/strict';
import { buildConfig, buildCommands } from '../lib/config-builder.mjs';
const valid = {
  model: 'exact-model',
  childModel: 'child-model',
  endpoint: 'https://example.com/v1/chat/completions',
  keyEnv: 'MODEL_API_KEY',
};
test('English commands and validation messages respect locale', () => {
  assert.match(buildCommands('formal', 3, 'en'), /Run from/);
  assert.doesNotMatch(buildCommands('formal', 3, 'en'), /[\u3400-\u9fff]/);
  assert.throws(
    () => buildConfig({ ...valid, model: '' }, 'en'),
    /Enter the main model ID/,
  );
  assert.throws(
    () => buildConfig({ ...valid, endpoint: 'bad' }, 'en'),
    /valid API URL/,
  );
  assert.throws(() => buildCommands('formal', 1, 'en'), /three repetitions/);
});
test('configuration uses env references, paired canonical launcher and isolated workspace', () => {
  const yaml = buildConfig(valid);
  assert.match(yaml, /workspace_mode: container_clone/);
  assert.match(yaml, /api_key_env: "MODEL_API_KEY"/);
  assert.doesNotMatch(yaml, /child_pool_id/);
  assert.match(buildCommands('formal', 3), /run_main\.ps1/);
  assert.match(buildCommands('formal', 3), /-Repetitions 3/);
});
test('reject unsafe environment names, missing model, embedded credentials and invalid repetitions', () => {
  assert.throws(() => buildConfig({ ...valid, keyEnv: 'x\nsecret' }));
  assert.throws(() => buildConfig({ ...valid, model: '' }));
  assert.throws(() =>
    buildConfig({ ...valid, endpoint: 'https://user:pass@example.com' }),
  );
  assert.throws(() => buildCommands('formal', 0));
  assert.throws(() => buildCommands('formal', 1));
});
test('model strings cannot inject YAML fields or PowerShell', () => {
  const yaml = buildConfig({ ...valid, model: 'x\nworkspace_mode: disabled' });
  assert.match(yaml, /main_model: "x\\nworkspace_mode: disabled"/);
  assert.equal(
    yaml.split('\n').filter((l) => l === 'workspace_mode: disabled').length,
    0,
  );
  assert.doesNotMatch(buildCommands('formal', 3), /x\nworkspace_mode/);
});

test('child model defaults to main without a fixed pool condition', () => {
  const yaml = buildConfig({ ...valid, childModel: '' });
  assert.match(yaml, /child_model: "exact-model"/);
  assert.doesNotMatch(yaml, /child_pool/);
});
test('provider options support a separate child endpoint without credentials', () => {
  const yaml = buildConfig({
    ...valid,
    childEndpoint: 'https://child.example.com/v1/chat/completions',
    childKeyEnv: 'CHILD_API_KEY',
    maxTokensParameter: 'max_tokens',
    sendSeed: false,
  });
  assert.match(yaml, /send_seed: false/);
  assert.match(yaml, /max_tokens_parameter: max_tokens/);
  assert.match(yaml, /child_provider:[\s\S]*api_key_env: "CHILD_API_KEY"/);
  assert.throws(() =>
    buildConfig({
      ...valid,
      childEndpoint: 'https://secret:password@example.com',
    }),
  );
  assert.throws(() =>
    buildConfig({ ...valid, maxTokensParameter: 'injected\nsetting' }),
  );
  assert.throws(() => buildConfig({ ...valid, sendSeed: 'false' }));
});
