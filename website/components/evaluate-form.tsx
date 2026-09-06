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
          {copied ? <Check size={14} /> : <Copy size={14} />}{' '}
          {failed ? '请手动选择复制' : copied ? '已复制' : '复制'}
        </button>
      </div>
      <pre>{text}</pre>
    </div>
  );
}
export function EvaluateForm() {
  const queryTrack = useSearchParams().get('track');
  const initialTrack = queryTrack === 'b' ? 'b' : 'a';
  return <EvaluationWorkspace key={initialTrack} initialTrack={initialTrack} />;
}
function EvaluationWorkspace({ initialTrack }: { initialTrack: string }) {
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
  const [error, setError] = useState('');
  const [message, setMessage] = useState('');
  const [framework, setFramework] = useState('claude-code');
  const [component, setComponent] = useState('default');
  const [simStep, setSimStep] = useState(-1);
  useEffect(() => {
    if (simStep < 0 || simStep >= 3) return;
    const timer = setTimeout(() => setSimStep((s) => s + 1), 900);
    return () => clearTimeout(timer);
  }, [simStep]);
  const config = useMemo(() => {
    try {
      return buildConfig({
        model: model || 'replace-with-exact-model-id',
        childModel,
        endpoint,
        keyEnv,
        childEndpoint,
        childKeyEnv,
        maxTokensParameter,
        sendSeed: sendSeed === 'true',
      });
    } catch (e) {
      return '# ' + (e as Error).message;
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
  ]);
  const commands = buildCommands(
    scope,
    scope === 'formal' ? 3 : Number(repetitions),
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
    try {
      const text = buildConfig({
        model,
        childModel,
        endpoint,
        keyEnv,
        childEndpoint,
        childKeyEnv,
        maxTokensParameter,
        sendSeed: sendSeed === 'true',
      });
      download('model-config.yaml', text);
      setError('');
      setMessage('配置已生成。下载运行脚本后，在本地仓库根目录执行。');
    } catch (e) {
      setError((e as Error).message);
      setMessage('');
    }
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
          Track A · 模型 API
        </TabsTrigger>
        <TabsTrigger value="b" className="tab-trigger">
          Track B · 模拟预览
        </TabsTrigger>
      </TabsList>
      <TabsContent value="a">
        <div className="note">
          <span>
            评测在参与者电脑上运行。API
            密钥留在本地，官网提供配置、教程和结果展示。
          </span>
        </div>
        <div className="evaluation-grid">
          <div className="panel form-section">
            <h3>模型配置</h3>
            <p className="form-intro">
              适用于当前参考 scaffold 的 OpenAI-compatible
              API。子模型默认与主模型相同，可按实际运行需要另行配置。
            </p>
            <label className="field">
              <span>API 地址</span>
              <input
                type="url"
                value={endpoint}
                onChange={(e) => setEndpoint(e.target.value)}
                spellCheck={false}
              />
            </label>
            <div className="form-row">
              <label className="field">
                <span>主模型 ID</span>
                <input
                  value={model}
                  onChange={(e) => setModel(e.target.value)}
                  placeholder="填写精确模型版本"
                  spellCheck={false}
                />
              </label>
              <label className="field">
                <span>子模型 ID（可选）</span>
                <input
                  value={childModel}
                  onChange={(e) => setChildModel(e.target.value)}
                  placeholder="留空则使用主模型"
                  spellCheck={false}
                />
              </label>
            </div>
            <label className="field">
              <span>密钥环境变量名</span>
              <input
                value={keyEnv}
                onChange={(e) => setKeyEnv(e.target.value)}
                spellCheck={false}
              />
              <small>只填写变量名。实际密钥在运行机器的终端中设置。</small>
            </label>
            <details className="provider-options">
              <summary>服务商选项</summary>
              <label className="field">
                <span>子模型 API 地址（可选）</span>
                <input
                  type="url"
                  value={childEndpoint}
                  onChange={(e) => setChildEndpoint(e.target.value)}
                  placeholder="默认使用上方 API 地址"
                  spellCheck={false}
                />
              </label>
              <label className="field">
                <span>子模型密钥环境变量（可选）</span>
                <input
                  value={childKeyEnv}
                  onChange={(e) => setChildKeyEnv(e.target.value)}
                  placeholder="默认使用上方环境变量"
                  spellCheck={false}
                />
              </label>
              {choice(
                '输出长度参数',
                maxTokensParameter,
                setMaxTokensParameter,
                [
                  ['max_completion_tokens', 'max_completion_tokens'],
                  ['max_tokens', 'max_tokens'],
                ],
              )}
              {choice('向 API 传递 seed', sendSeed, setSendSeed, [
                ['true', '是'],
                ['false', '否'],
              ])}
              <p className="muted">
                按服务商支持的参数选择。运行脚本会在本地执行服务连接预检。
              </p>
            </details>
            <div className="form-row">
              {choice('评测集合', scope, setScope, [
                ['development', '单任务试跑'],
                ['formal', '主实验'],
              ])}
              {scope === 'formal' ? (
                <label className="field">
                  <span>重复次数</span>
                  <input value="固定 3 次 / 每种模式" readOnly />
                </label>
              ) : (
                choice('重复次数', repetitions, setRepetitions, [
                  ['1', '1 次'],
                  ['3', '3 次'],
                  ['5', '5 次'],
                ])
              )}
            </div>
            <div className="checkline">
              固定参考 harness · Linear / Async 配对
            </div>
            <div className="checkline">
              容器工作区 · 主模型 100 步 / 子模型 40 步
            </div>
            <div className="actions">
              <button className="btn primary" onClick={saveConfig}>
                <Download size={16} />
                下载配置
              </button>
              <button
                className="btn secondary"
                onClick={() => download('run-evaluation.ps1', commands)}
              >
                下载运行脚本
              </button>
            </div>
            {error && (
              <p className="error-text" role="alert">
                {error}
              </p>
            )}
            {message && <output className="checkline">{message}</output>}
            <p
              className="form-intro"
              style={{ marginTop: 20, marginBottom: 0 }}
            >
              需要仓库访问权限及对应任务资源。下载配置不代表获得正式上榜资格。
              <Link className="text-link" href="/docs#track-a">
                阅读 Track A 教程 <ArrowRight size={14} />
              </Link>
            </p>
          </div>
          <div>
            <CodeBlock text={commands} title="POWERSHELL 7" />
            <div style={{ marginTop: 20 }}>
              <CodeBlock text={config} title="MODEL-CONFIG.YAML" />
            </div>
            <div className="panel" style={{ marginTop: 20 }}>
              <h3>运行后提交结果</h3>
              <p className="form-intro" style={{ marginTop: 12 }}>
                使用提交工具打包并校验公开摘要，再通过 GitHub
                提交。维护者审核记录合并后，榜单自动更新。
              </p>
              <a className="text-link" href={submissionUrl}>
                提交 Track A 结果 <ArrowRight size={14} />
              </a>
              <p className="form-intro" style={{ marginTop: 12 }}>
                表单内容公开可见，请先核对
                <Link className="text-link" href="/docs#submission">
                  提交说明
                </Link>
                。提交不会自动生成已验证成绩。
              </p>
            </div>
          </div>
        </div>
      </TabsContent>
      <TabsContent value="b">
        <div className="note amber">
          <span>
            模拟预览：以下操作只在当前浏览器演示配置流程，不连接框架、不调用模型、不生成测评分数。
          </span>
        </div>
        <div className="evaluation-grid">
          <div className="panel form-section">
            <h3>选择框架与策略组件</h3>
            <p className="form-intro">
              预集成与自定义系统均通过统一驱动接入评测内核。
            </p>
            {choice(
              'Agent 系统',
              framework,
              (v) => {
                setFramework(v);
                setSimStep(-1);
              },
              [
                ['claude-code', 'Claude Code · 计划集成'],
                ['langgraph', 'LangGraph 参考 Agent · 计划集成'],
                ['custom', '自定义 Agent · 接口预览'],
              ],
            )}
            {choice(
              '自定义组件',
              component,
              (v) => {
                setComponent(v);
                setSimStep(-1);
              },
              [
                ['default', '使用框架默认策略'],
                ['context', 'ContextBuilder · 上下文管理'],
                ['delegation', 'DelegationPolicy · 子任务策略'],
                ['policy', 'AgentPolicy · 主 Agent 决策'],
              ],
            )}
            <div className="simulation">
              固定内核继续掌握事件交付、工作区和评分。组件只能决定如何处理已释放的信息。
            </div>
            <button
              className="btn primary"
              style={{ marginTop: 24 }}
              disabled={simStep >= 0 && simStep < 3}
              onClick={() => setSimStep(0)}
            >
              {simStep === 3 ? '重新模拟' : '演示接入流程'}
            </button>
          </div>
          <div className="panel">
            <span className="tag">模拟预览 · 无真实执行</span>
            <h3 style={{ fontSize: 20, marginTop: 18 }}>接入流程预览</h3>
            <div className="sim-steps">
              {[
                '读取框架配置',
                '演示协议兼容性检查',
                '演示 Linear / Async 任务创建',
                '模拟完成 · 未生成真实结果',
              ].map((s, i) => (
                <div
                  key={s}
                  className={'sim-step ' + (simStep >= i ? 'done' : 'muted')}
                >
                  <span className="mono">
                    {simStep > i || simStep === 3
                      ? '✓'
                      : String(i + 1).padStart(2, '0')}
                  </span>
                  {s}
                  {simStep === i && i < 3 ? ' …' : ''}
                </div>
              ))}
            </div>
            <output
              className="muted"
              style={{ display: 'block', fontSize: 13, marginTop: 24 }}
            >
              {simStep === 3
                ? '这次模拟没有通过真实协议测试，也不会进入排行榜。'
                : '选择一个系统，查看后续接入流程。'}
            </output>
            <Link
              className="text-link"
              style={{ marginTop: 20 }}
              href="/docs#track-b"
            >
              查看 Track B 接口说明 <ArrowRight size={14} />
            </Link>
          </div>
        </div>
      </TabsContent>
    </Tabs>
  );
}
