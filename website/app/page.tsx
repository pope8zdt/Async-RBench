import Link from 'next/link';
import {
  ArrowRight,
  ArrowUpRight,
  Box,
  FlaskConical,
  Layers3,
  Terminal,
  Workflow,
} from 'lucide-react';
import { themes, metrics } from '@/lib/content';
import data from '@/public/data/experiments.json';
export default function Home() {
  return (
    <div className="page-wrap">
      <section className="overview-top">
        <div>
          <div className="eyebrow">
            <span className="status-dot" /> ASYNCHRONOUS AGENT EVALUATION
          </div>
          <h1>
            当结果陆续到达，
            <br />
            Agent 能否<span className="accent">重新规划？</span>
          </h1>
          <p className="lead">
            在相同任务的 Linear / Async 条件下，评测主 Agent
            如何整合子任务结果、识别变化，并完成可验证的目标。
          </p>
          <div className="actions">
            <Link href="/evaluate" className="btn primary">
              开始评测 <ArrowRight size={17} />
            </Link>
            <Link href="/leaderboard" className="btn secondary">
              查看实验记录 <ArrowUpRight size={17} />
            </Link>
          </div>
        </div>
        <div
          className="protocol-diagram"
          aria-label="评测协议示意图，非真实运行轨迹"
        >
          <div className="diagram-top">
            <span className="mono">ONE TASK. TWO CONDITIONS.</span>
            <span className="tag">协议示意</span>
          </div>
          <div className="flow-label">
            <span>LINEAR</span>
            <span>顺序执行</span>
          </div>
          <div className="linear-flow">
            <span>主 Agent</span>
            <i />
            <span>子任务</span>
            <i />
            <span>验证</span>
          </div>
          <div className="flow-label">
            <span>ASYNC</span>
            <span>受控事件交付</span>
          </div>
          <div className="async-flow">
            <div className="flow-main">
              主 Agent <Workflow size={18} />
            </div>
            <div className="flow-children">
              <span>
                子任务 A <span className="pill-line" />
              </span>
              <span>
                子任务 B <span className="pill-line blue" />
              </span>
              <span>
                子任务 C <span className="pill-line short" />
              </span>
            </div>
            <div className="flow-gateway">
              结果网关 <ArrowRight size={15} /> 重规划 <ArrowRight size={15} />{' '}
              验证
            </div>
          </div>
          <p className="diagram-note">事件时序由内核控制 · 策略由 Agent 决定</p>
        </div>
      </section>
      <div className="stats-strip">
        {[
          ['201', '注册实例'],
          ['8', '事件主题'],
          ['2', '配对执行条件'],
          [String(data.records.length), '真实结果快照'],
        ].map(([n, t]) => (
          <div key={t}>
            <strong>{n}</strong>
            <span>{t}</span>
          </div>
        ))}
      </div>
      <section className="section">
        <div className="section-heading">
          <div>
            <div className="eyebrow">PARTICIPATE</div>
            <h2>选择你的参评方式</h2>
          </div>
          <Link className="text-link" href="/docs#tracks">
            了解两条赛道 <ArrowUpRight size={16} />
          </Link>
        </div>
        <div className="note" style={{ marginBottom: 24 }}>
          <Terminal size={18} />
          <span>
            网页配置 → 参与者电脑运行 → 提交结果 → 审核后更新榜单。Track B
            当前为流程模拟。
          </span>
        </div>
        <div className="track-grid">
          <Link href="/evaluate?track=a" className="track-card">
            <div className="card-top">
              <Terminal />
              <span className="tag green">真实配置</span>
            </div>
            <span className="mono muted">TRACK A / MODEL</span>
            <h3>评测模型能力</h3>
            <p>
              在固定参考 harness 下接入模型 API，生成与当前评测入口兼容的配置。
            </p>
            <div className="card-footer">
              <span>模型 API · 固定编排 · 配对评测</span>
              <ArrowRight size={19} />
            </div>
          </Link>
          <Link href="/evaluate?track=b" className="track-card dark">
            <div className="card-top">
              <Box />
              <span className="tag purple">模拟预览</span>
            </div>
            <span className="mono">TRACK B / AGENT SYSTEM</span>
            <h3>评测完整 Agent 系统</h3>
            <p>
              预览 Claude Code、LangGraph
              和自定义组件的接入流程。当前不执行真实评测。
            </p>
            <div className="card-footer">
              <span>预集成框架 · 可定制策略</span>
              <ArrowRight size={19} />
            </div>
          </Link>
        </div>
      </section>
      <section className="section">
        <div className="section-heading">
          <div>
            <div className="eyebrow">MEASUREMENT</div>
            <h2>三个独立指标，观察不同能力</h2>
          </div>
          <Link className="text-link" href="/docs#metrics">
            指标定义 <ArrowUpRight size={16} />
          </Link>
        </div>
        <div className="metric-grid">
          {metrics.map((m, i) => (
            <div className="metric-card" key={m.name}>
              <span className="metric-number">0{i + 1}</span>
              <h3>{m.name}</h3>
              <strong>{m.full}</strong>
              <p>{m.description}</p>
            </div>
          ))}
        </div>
        <div className="note">
          <FlaskConical size={18} />
          <span>
            核心指标按事件主题等权宏平均。当前 61
            实例实验集合包含不同数据划分，不等同于完整 held-out 榜单。
          </span>
        </div>
      </section>
      <section className="section">
        <div className="section-heading">
          <div>
            <div className="eyebrow">EVENT TAXONOMY</div>
            <h2>八类事件，检验计划如何改变</h2>
          </div>
          <Layers3 className="muted" />
        </div>
        <div className="theme-grid">
          {themes.map(([id, title, desc], i) => (
            <div className="theme-item" key={id}>
              <span className="mono">{String(i + 1).padStart(2, '0')}</span>
              <div>
                <h4>{title}</h4>
                <p>{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
