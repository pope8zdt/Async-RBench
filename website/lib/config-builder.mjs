export function buildConfig({
  model,
  childModel,
  endpoint,
  keyEnv,
  childPool,
}) {
  if (!model?.trim() || !childModel?.trim() || !childPool?.trim())
    throw new Error('请填写主模型、子模型和固定子模型池标识。');
  if (!/^[A-Z_][A-Z0-9_]*$/.test(keyEnv))
    throw new Error('密钥环境变量只允许大写字母、数字和下划线。');
  let url;
  try {
    url = new URL(endpoint);
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
  const q = JSON.stringify;
  return `# Async-RBench v11.0.0 — reference scaffold\n# Credentials stay in your local environment.\nbackend: openai_compatible\napi_url: ${q(endpoint)}\napi_key_env: ${q(keyEnv)}\napi_key_required: true\nmain_model: ${q(model)}\nchild_model: ${q(childModel)}\nchild_pool_id: ${q(childPool)}\ntemperature: null\nmax_output_tokens: 16384\nmax_tokens_parameter: max_completion_tokens\nsend_seed: true\nmain_provider:\n  backend: openai_compatible\n  api_url: ${q(endpoint)}\n  api_key_env: ${q(keyEnv)}\n  max_api_concurrency: 4\n  max_tokens_parameter: max_completion_tokens\nchild_provider:\n  backend: openai_compatible\n  api_url: ${q(endpoint)}\n  api_key_env: ${q(keyEnv)}\n  max_api_concurrency: 4\n  max_tokens_parameter: max_completion_tokens\nmax_main_steps: 100\nmax_child_steps: 40\nmax_concurrent_children: 3\nmax_total_child_spawns: 5\nmax_api_concurrency: 4\nemergency_total_token_cap: 5000000\nmain_terminal_timeout_sec: 180\nchild_terminal_timeout_sec: 180\nchild_timeout_sec: 1200\nstart_barrier_timeout_sec: 120\nlive_cancellation_grace_sec: 60\nworkspace_mode: container_clone\nkeep_child_workspaces: false\nmax_tool_output_chars: 20000\nrequest_timeout_sec: 600\n`;
}
export function buildCommands(scope, repetitions) {
  if (!Number.isInteger(repetitions) || repetitions < 1 || repetitions > 10)
    throw new Error('重复次数须为 1–10 的整数。');
  if (!['formal', 'development'].includes(scope))
    throw new Error('未知评测集合。');
  const run =
    scope === 'formal'
      ? `.\\experiments\\formal-61\\run.ps1 -Config "model-config.yaml" -Repetitions ${repetitions} -Seed 2026`
      : `.\\run_case.ps1 -Instance "secure-release::seed-1" -Config "model-config.yaml" -Repetitions ${repetitions} -Seed 2026`;
  return (
    '# 在已安装 Async-RBench 的仓库根目录运行（PowerShell 7）\n# 将 model-config.yaml 放在仓库根目录，并在终端设置配置所指向的密钥环境变量。\npython -m async_rbench.cli validate --release\npython -m async_rbench.paper_eval check --root .\n' +
    run +
    '\n'
  );
}
