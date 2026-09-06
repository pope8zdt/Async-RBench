function apiUrl(value) {
  let url;
  try {
    url = new URL(value);
  } catch {
    throw new Error('请输入有效的 API 地址。');
  }
  if (
    !['https:', 'http:'].includes(url.protocol) ||
    url.username ||
    url.password ||
    url.search ||
    url.hash
  )
    throw new Error('API 地址不能包含凭据、查询参数或片段。');
  return value;
}
function envName(value) {
  if (!/^[A-Z_][A-Z0-9_]*$/.test(value))
    throw new Error('密钥环境变量只允许大写字母、数字和下划线。');
  return value;
}
export function buildConfig({
  model,
  childModel = '',
  endpoint,
  keyEnv,
  childEndpoint = '',
  childKeyEnv = '',
  maxTokensParameter = 'max_completion_tokens',
  sendSeed = true,
}) {
  if (!model?.trim()) throw new Error('请填写主模型 ID。');
  apiUrl(endpoint);
  envName(keyEnv);
  const childUrl = apiUrl(childEndpoint || endpoint);
  const childKey = envName(childKeyEnv || keyEnv);
  if (
    !['max_tokens', 'max_completion_tokens'].includes(maxTokensParameter) ||
    typeof sendSeed !== 'boolean'
  )
    throw new Error('无效的服务商参数选项。');
  const q = JSON.stringify;
  return `# Async-RBench v11.0.0 — reference scaffold
# Credentials stay in your local environment.
backend: openai_compatible
api_url: ${q(endpoint)}
api_key_env: ${q(keyEnv)}
api_key_required: true
main_model: ${q(model)}
child_model: ${q(childModel.trim() || model)}
temperature: null
max_output_tokens: 16384
max_tokens_parameter: ${maxTokensParameter}
send_seed: ${sendSeed}
main_provider:
  backend: openai_compatible
  api_url: ${q(endpoint)}
  api_key_env: ${q(keyEnv)}
  max_api_concurrency: 4
  max_tokens_parameter: ${maxTokensParameter}
child_provider:
  backend: openai_compatible
  api_url: ${q(childUrl)}
  api_key_env: ${q(childKey)}
  max_api_concurrency: 4
  max_tokens_parameter: ${maxTokensParameter}
max_main_steps: 100
max_child_steps: 40
max_concurrent_children: 3
max_total_child_spawns: 5
max_api_concurrency: 4
emergency_total_token_cap: 5000000
main_terminal_timeout_sec: 180
child_terminal_timeout_sec: 180
child_timeout_sec: 1200
start_barrier_timeout_sec: 120
live_cancellation_grace_sec: 60
workspace_mode: container_clone
keep_child_workspaces: false
max_tool_output_chars: 20000
request_timeout_sec: 600
`;
}

export function buildCommands(scope, repetitions) {
  if (!Number.isInteger(repetitions) || repetitions < 1 || repetitions > 10)
    throw new Error('重复次数须为 1–10 的整数。');
  if (!['formal', 'development'].includes(scope))
    throw new Error('未知评测集合。');
  if (scope === 'formal' && repetitions !== 3)
    throw new Error('主实验 47 case 固定为每种模式 3 次重复。');
  const run =
    scope === 'formal'
      ? `.\\experiments\\formal-47\\run.ps1 -Config "model-config.yaml" -Repetitions ${repetitions} -Seed 2026`
      : `.\\run_case.ps1 -Instance "secure-release::seed-1" -Config "model-config.yaml" -Repetitions ${repetitions} -Seed 2026`;
  return (
    '# 在已安装 Async-RBench 的仓库根目录运行（PowerShell 7）\n# 将 model-config.yaml 放在仓库根目录，并在终端设置配置所指向的密钥环境变量。\npython -m async_rbench.cli validate --release\npython -m async_rbench.main_experiment check --root .\n' +
    run +
    '\n'
  );
}
