export const TRACK_B_FRAMEWORKS = [
  { id: 'claude-code', label: 'Claude Code' },
  { id: 'codex-cli', label: 'Codex CLI' },
  { id: 'langgraph', label: 'LangGraph' },
  { id: 'openai-agents', label: 'OpenAI Agents SDK' },
];

const imageTargets = {
  'claude-code': 'claude',
  'codex-cli': 'codex',
  langgraph: 'langgraph',
  'openai-agents': 'openai',
};

const components = {
  context: ['context_builder', 'my_harness.components:build_context'],
  delegation: ['delegation_policy', 'my_harness.components:build_delegation'],
  policy: ['agent_policy', 'my_harness.components:build_agent_policy'],
  backend: ['model_backend', 'my_harness.components:build_model_backend'],
  hooks: ['lifecycle_hooks', 'my_harness.components:build_hooks'],
};

function scalar(value) {
  const text = String(value || '').trim();
  if (!text || /[\s:#{}[\],&*!|>'"%@`]/.test(text)) {
    return JSON.stringify(text);
  }
  return text;
}

export function buildTrackBConfig({
  framework,
  model,
  credentialEnv,
  component = 'default',
}) {
  if (!TRACK_B_FRAMEWORKS.some(({ id }) => id === framework)) {
    throw new Error(`Unknown Track B framework: ${framework}`);
  }
  const imageTarget = imageTargets[framework];
  const lines = [
    'track: B',
    `framework: ${framework}`,
    `model: ${scalar(model || 'replace-with-exact-model-id')}`,
    `credential_env: ${scalar(framework === 'codex-cli' ? '' : credentialEnv || '')}`,
    'runtime:',
    '  type: docker',
    `  image: async-rbench-track-b:${imageTarget}`,
    '  cpus: 0.5',
    '  memory: 768m',
    '  timeout_sec: 2400',
  ];
  if (component !== 'default') {
    const entry = components[component];
    if (!entry) throw new Error(`Unknown Track B component: ${component}`);
    lines.push('components:', `  ${entry[0]}: ${entry[1]}`);
  }
  lines.push(
    'limits:',
    '  max_main_steps: 100',
    '  max_child_steps: 40',
    '  max_concurrent_children: 3',
    '  max_total_child_spawns: 5',
    '  request_timeout_sec: 600',
  );
  return `${lines.join('\n')}\n`;
}

function powershellArgument(value) {
  return `"${String(value).replace(/`/g, '``').replace(/"/g, '`"')}"`;
}

export function buildTrackBCommands(
  configName = 'track-b-config.yaml',
  model = 'replace-with-exact-model-id',
  framework = 'claude-code',
) {
  const imageTarget = imageTargets[framework];
  if (!imageTarget) throw new Error(`Unknown Track B framework: ${framework}`);
  const modelArgument = powershellArgument(
    model || 'replace-with-exact-model-id',
  );
  return [
    `python docker\\track-b\\build.py ${imageTarget}`,
    `python -m async_rbench.track_b doctor --config "${configName}"`,
    `python -m async_rbench.track_b conformance --config "${configName}" --output "artifacts/track-b/conformance" --cases "secure-release"`,
    `python -m async_rbench.track_b make-manifest --instances "secure-release::seed-1" --model ${modelArgument} --output "artifacts/track-b/manifest.json"`,
    `python -m async_rbench.track_b run --config "${configName}" --manifest "artifacts/track-b/manifest.json" --output "artifacts/track-b/runs"`,
    '$benchmarkCommit = git rev-parse HEAD',
    `python -m async_rbench.track_b package --runs "artifacts/track-b/runs" --manifest "artifacts/track-b/manifest.json" --benchmark-commit $benchmarkCommit --output "artifacts/track-b/public-result.json"`,
    'python -m async_rbench.track_b validate-package --input "artifacts/track-b/public-result.json"',
  ].join('\n');
}
