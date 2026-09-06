'use client';
import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { ArrowRight, Check, Copy, Download } from 'lucide-react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select';
import { useCopy, usePreferences } from '@/components/preferences';
import { buildConfig, buildCommands } from '@/lib/config-builder.mjs';
import { submissionUrl } from '@/lib/repository';

function download(name: string, text: string) {
  const url = URL.createObjectURL(
    new Blob([text], { type: 'text/plain;charset=utf-8' }),
  );
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}

export function CodeBlock({ text, title }: { text: string; title: string }) {
  const copy = useCopy();
  const [copied, setCopied] = useState(false);
  const [failed, setFailed] = useState(false);
  return (
    <div className="code-panel">
      <div className="code-header">
        <span className="mono">{title}</span>
        <button
          onClick={async () => {
            try {
              await navigator.clipboard.writeText(text);
              setCopied(true);
              setFailed(false);
              setTimeout(() => setCopied(false), 1800);
            } catch {
              setFailed(true);
            }
          }}
        >
          {copied ? <Check size={14} /> : <Copy size={14} />}
          {failed
            ? copy('请手动复制', 'Copy manually')
            : copied
              ? copy('已复制', 'Copied')
              : copy('复制', 'Copy')}
        </button>
      </div>
      <pre>{text}</pre>
    </div>
  );
}

export function EvaluateForm() {
  const initialTrack = useSearchParams().get('track') === 'b' ? 'b' : 'a';
  return <EvaluationWorkspace key={initialTrack} initialTrack={initialTrack} />;
}

function EvaluationWorkspace({ initialTrack }: { initialTrack: string }) {
  const copy = useCopy();
  const { locale } = usePreferences();
  const [track, setTrack] = useState(initialTrack);
  const [model, setModel] = useState('');
  const [childModel, setChildModel] = useState('');
  const [endpoint, setEndpoint] = useState(
    'https://api.openai.com/v1/chat/completions',
  );
  const [keyEnv, setKeyEnv] = useState('MODEL_API_KEY');
  const [childEndpoint, setChildEndpoint] = useState('');
  const [childKeyEnv, setChildKeyEnv] = useState('');
  const [maxTokensParameter, setMaxTokensParameter] = useState(
    'max_completion_tokens',
  );
  const [sendSeed, setSendSeed] = useState('true');
  const [scope, setScope] = useState('development');
  const [repetitions, setRepetitions] = useState('1');
  const [attempted, setAttempted] = useState(false);
  const [saved, setSaved] = useState(false);
  const [framework, setFramework] = useState('claude-code');
  const [component, setComponent] = useState('default');
  const [simStep, setSimStep] = useState(-1);

  useEffect(() => {
    if (simStep < 0 || simStep >= 3) return;
    const timer = setTimeout(() => setSimStep((s) => s + 1), 900);
    return () => clearTimeout(timer);
  }, [simStep]);

  const config = useMemo(() => {
    const options = {
      model,
      childModel,
      endpoint,
      keyEnv,
      childEndpoint,
      childKeyEnv,
      maxTokensParameter,
      sendSeed: sendSeed === 'true',
    };
    let error = '';
    try {
      buildConfig(options, locale);
    } catch (e) {
      error = (e as Error).message;
    }
    try {
      return {
        text: buildConfig(
          { ...options, model: model || 'replace-with-exact-model-id' },
          locale,
        ),
        error,
      };
    } catch (e) {
      return { text: '# ' + (e as Error).message, error };
    }
  }, [
    model,
    childModel,
    endpoint,
    keyEnv,
    childEndpoint,
    childKeyEnv,
    maxTokensParameter,
    sendSeed,
    locale,
  ]);
  const commands = buildCommands(
    scope,
    scope === 'formal' ? 3 : Number(repetitions),
    locale,
  );

  const choice = (
    label: string,
    value: string,
    set: (v: string) => void,
    items: string[][],
  ) => (
    <label className="field">
      <span>{label}</span>
      <Select value={value} onValueChange={(v) => set(v ?? items[0][0])}>
        <SelectTrigger
          className="select-trigger"
          style={{ width: '100%' }}
          aria-label={label}
        >
          <SelectValue>{items.find(([id]) => id === value)?.[1]}</SelectValue>
        </SelectTrigger>
        <SelectContent>
          {items.map(([v, l]) => (
            <SelectItem key={v} value={v}>
              {l}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </label>
  );

  function saveConfig() {
    setAttempted(true);
    setSaved(!config.error);
    if (!config.error) download('model-config.yaml', config.text);
  }

  return (
    <Tabs
      value={track}
      onValueChange={(v) => {
        setTrack(String(v));
        setSimStep(-1);
      }}
    >
      <TabsList className="tab-list">
        <TabsTrigger value="a" className="tab-trigger">
          Track A · {copy('模型 API', 'Model API')}
        </TabsTrigger>
        <TabsTrigger value="b" className="tab-trigger">
          Track B · {copy('模拟预览', 'Simulation')}
        </TabsTrigger>
      </TabsList>
      <TabsContent value="a">
        <div className="evaluation-grid">
          <div className="panel form-section">
            <h3>{copy('模型配置', 'Model configuration')}</h3>
            <label className="field">
              <span>{copy('模型 ID', 'Model ID')}</span>
              <input
                value={model}
                onChange={(e) => setModel(e.target.value)}
                placeholder={copy('填写精确版本', 'Exact model version')}
                spellCheck={false}
              />
            </label>
            <label className="field">
              <span>{copy('API 地址', 'API URL')}</span>
              <input
                type="url"
                value={endpoint}
                onChange={(e) => setEndpoint(e.target.value)}
                spellCheck={false}
              />
            </label>
            <label className="field">
              <span>
                {copy('密钥环境变量名', 'API key environment variable')}
              </span>
              <input
                value={keyEnv}
                onChange={(e) => setKeyEnv(e.target.value)}
                spellCheck={false}
              />
            </label>
            <details className="provider-options">
              <summary>
                {copy('子模型与服务商选项', 'Child model & provider options')}
              </summary>
              <label className="field">
                <span>{copy('子模型 ID', 'Child model ID')}</span>
                <input
                  value={childModel}
                  onChange={(e) => setChildModel(e.target.value)}
                  placeholder={copy('默认使用主模型', 'Defaults to main model')}
                  spellCheck={false}
                />
              </label>
              <label className="field">
                <span>{copy('子模型 API 地址', 'Child API URL')}</span>
                <input
                  type="url"
                  value={childEndpoint}
                  onChange={(e) => setChildEndpoint(e.target.value)}
                  placeholder={copy(
                    '默认使用主模型地址',
                    'Defaults to main API URL',
                  )}
                  spellCheck={false}
                />
              </label>
              <label className="field">
                <span>
                  {copy(
                    '子模型密钥环境变量',
                    'Child API key environment variable',
                  )}
                </span>
                <input
                  value={childKeyEnv}
                  onChange={(e) => setChildKeyEnv(e.target.value)}
                  placeholder={copy(
                    '默认使用主模型变量',
                    'Defaults to main key variable',
                  )}
                  spellCheck={false}
                />
              </label>
              {choice(
                copy('输出长度参数', 'Output limit parameter'),
                maxTokensParameter,
                setMaxTokensParameter,
                [
                  ['max_completion_tokens', 'max_completion_tokens'],
                  ['max_tokens', 'max_tokens'],
                ],
              )}
              {choice(copy('传递 seed', 'Send seed'), sendSeed, setSendSeed, [
                ['true', copy('是', 'Yes')],
                ['false', copy('否', 'No')],
              ])}
            </details>
            <div className="form-row">
              {choice(copy('评测集合', 'Evaluation scope'), scope, setScope, [
                ['development', copy('单任务试跑', 'Single-task trial')],
                ['formal', copy('主实验', 'Main experiment')],
              ])}
              {scope === 'formal' ? (
                <label className="field">
                  <span>{copy('重复次数', 'Repetitions')}</span>
                  <input
                    value={copy('每种模式固定 3 次', '3 per mode (fixed)')}
                    readOnly
                  />
                </label>
              ) : (
                choice(
                  copy('重复次数', 'Repetitions'),
                  repetitions,
                  setRepetitions,
                  [
                    ['1', '1'],
                    ['3', '3'],
                    ['5', '5'],
                  ],
                )
              )}
            </div>
            <p>
              {copy(
                '在本地运行，密钥留在本地。此处只填写环境变量名。',
                'Run locally. Keep keys local; enter only the environment variable name here.',
              )}
            </p>
            <div className="actions">
              <button className="btn primary" onClick={saveConfig}>
                <Download size={16} />
                {copy('下载配置', 'Download config')}
              </button>
              <button
                className="btn secondary"
                onClick={() => download('run-evaluation.ps1', commands)}
              >
                {copy('下载脚本', 'Download script')}
              </button>
            </div>
            {attempted && config.error && (
              <p className="error-text" role="alert">
                {config.error}
              </p>
            )}
            {saved && !config.error && (
              <output>
                {copy('配置已下载。', 'Configuration downloaded.')}
              </output>
            )}
            <Link
              className="text-link"
              style={{ marginTop: 20 }}
              href="/docs#quickstart"
            >
              {copy('运行教程', 'Run tutorial')} <ArrowRight size={14} />
            </Link>
          </div>
          <div>
            <CodeBlock text={commands} title="POWERSHELL 7" />
            <details className="provider-options" style={{ marginTop: 20 }}>
              <summary>{copy('预览配置', 'Preview configuration')}</summary>
              <CodeBlock text={config.text} title="MODEL-CONFIG.YAML" />
            </details>
            <div className="panel" style={{ marginTop: 20 }}>
              <h3>{copy('提交结果', 'Submit results')}</h3>
              <p>
                {copy(
                  '提交公开汇总包。自报结果需经维护者审核。',
                  'Submit a public summary package. Self-reported results require maintainer review.',
                )}
              </p>
              <div className="actions">
                <a className="text-link" href={submissionUrl}>
                  {copy('打开提交表单', 'Open submission form')}{' '}
                  <ArrowRight size={14} />
                </a>
                <Link className="text-link" href="/docs#submission">
                  {copy('提交说明', 'Submission guide')}
                </Link>
              </div>
            </div>
          </div>
        </div>
      </TabsContent>
      <TabsContent value="b">
        <div className="note amber">
          {copy(
            '模拟预览：不调用模型、不生成真实结果，不具备上榜资格。',
            'Simulation only: no model calls, real results or leaderboard eligibility.',
          )}
        </div>
        <div className="evaluation-grid">
          <div className="panel form-section">
            <h3>{copy('Agent 系统', 'Agent system')}</h3>
            {choice(
              copy('框架', 'Framework'),
              framework,
              (v) => {
                setFramework(v);
                setSimStep(-1);
              },
              [
                [
                  'claude-code',
                  copy('Claude Code · 计划中', 'Claude Code · Planned'),
                ],
                [
                  'langgraph',
                  copy('LangGraph · 计划中', 'LangGraph · Planned'),
                ],
                [
                  'custom',
                  copy('自定义 Agent · 预览', 'Custom agent · Preview'),
                ],
              ],
            )}
            {choice(
              copy('策略组件', 'Policy component'),
              component,
              (v) => {
                setComponent(v);
                setSimStep(-1);
              },
              [
                ['default', copy('框架默认策略', 'Framework default')],
                ['context', 'ContextBuilder'],
                ['delegation', 'DelegationPolicy'],
                ['policy', 'AgentPolicy'],
              ],
            )}
            <button
              className="btn primary"
              style={{ marginTop: 20 }}
              disabled={simStep >= 0 && simStep < 3}
              onClick={() => setSimStep(0)}
            >
              {simStep === 3
                ? copy('重新模拟', 'Simulate again')
                : copy('开始模拟', 'Start simulation')}
            </button>
          </div>
          <div className="panel">
            <h3>{copy('模拟流程', 'Simulation workflow')}</h3>
            <div className="sim-steps" aria-live="polite">
              {[
                copy('读取框架配置', 'Read framework configuration'),
                copy('模拟协议检查', 'Simulate protocol checks'),
                copy(
                  '模拟 Linear / Async 创建',
                  'Simulate Linear / Async setup',
                ),
                copy(
                  '模拟完成 · 无真实结果',
                  'Simulation complete · No real results',
                ),
              ].map((step, i) => (
                <div
                  key={i}
                  className={'sim-step ' + (simStep >= i ? 'done' : 'muted')}
                >
                  <span className="mono">
                    {simStep > i || simStep === 3
                      ? '✓'
                      : String(i + 1).padStart(2, '0')}
                  </span>
                  {step}
                  {simStep === i && i < 3 ? ' …' : ''}
                </div>
              ))}
            </div>
            <Link
              className="text-link"
              style={{ marginTop: 20 }}
              href="/docs#track-b"
            >
              {copy('接口说明', 'Interface guide')} <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      </TabsContent>
    </Tabs>
  );
}
