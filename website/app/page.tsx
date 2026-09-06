import Link from 'next/link';
import { themes, metrics } from '@/lib/content';
import { repositoryUrl } from '@/lib/repository';
import data from '@/public/data/experiments.json';
import corpus from '@/public/data/corpus.json';

export default function Home() {
  return (
    <div className="page-wrap">
      <section className="overview-top">
        <div>
          <p className="overview-label">异步结果整合与动态重规划评测</p>
          <h1>Async-RBench</h1>
          <p className="lead">
            在相同任务的 Linear 与 Async 条件下，比较模型整合子任务结果、
            处理事件变化和完成任务的能力。201个高质量任务，覆盖{' '}
            {corpus.themes.length} 类事件主题。
          </p>
          <div className="actions">
            <Link href="/leaderboard" className="btn primary">
              查看榜单
            </Link>
            <Link href="/evaluate" className="btn secondary">
              开始评测
            </Link>
            <a href={repositoryUrl} className="text-link">
              GitHub ↗
            </a>
          </div>
        </div>
        <aside className="experiment-summary" aria-label="主实验设置">
          <h2>主实验设置</h2>
          <dl>
            <div>
              <dt>评测范围</dt>
              <dd>主实验任务清单 · 8 类事件</dd>
            </div>
            <div>
              <dt>执行条件</dt>
              <dd>Linear / Async</dd>
            </div>
            <div>
              <dt>重复次数</dt>
              <dd>每种模式 {data.cohort.repetitions} 次</dd>
            </div>
            <div>
              <dt>评分方式</dt>
              <dd>配对评分 · 主题等权汇总</dd>
            </div>
          </dl>
          <Link href="/docs#metrics" className="text-link">
            统计方法 ↗
          </Link>
        </aside>
      </section>

      <section className="section">
        <div className="section-heading">
          <h2>参与评测</h2>
          <Link className="text-link" href="/docs#quickstart">
            运行教程 ↗
          </Link>
        </div>
        <p className="section-intro">
          生成配置后在本地运行，完成后提交结果供审核。
        </p>
        <div className="track-grid">
          <Link href="/evaluate?track=a" className="track-card">
            <h3>
              Track A <span>模型 API</span>
            </h3>
            <p>在固定参考 harness 下接入模型，运行主实验的配对评测。</p>
            <span className="text-link">配置模型 ↗</span>
          </Link>
          <Link href="/evaluate?track=b" className="track-card">
            <h3>
              Track B <span>Agent 系统</span>
            </h3>
            <p>
              预留 Claude Code、LangGraph
              与自定义组件接入。目前仅提供流程模拟，不产生真实成绩。
            </p>
            <span className="text-link">查看模拟 ↗</span>
          </Link>
        </div>
      </section>

      <section className="section">
        <div className="section-heading">
          <h2>评测指标</h2>
          <Link className="text-link" href="/docs#metrics">
            指标定义 ↗
          </Link>
        </div>
        <dl className="metric-definitions">
          {metrics.map((m) => (
            <div key={m.name}>
              <dt>
                {m.name}
                <span>{m.full}</span>
              </dt>
              <dd>{m.description}</dd>
            </div>
          ))}
        </dl>
        <p className="section-footnote">
          按主实验清单与八类事件主题等权汇总。未完成的实验展示覆盖进度与暂计分数。
        </p>
      </section>

      <section className="section">
        <div className="section-heading">
          <h2>事件类型</h2>
          <Link className="text-link" href="/tasks">
            查看完整任务库 ↗
          </Link>
        </div>
        <p className="section-intro">
          201个高质量任务，按以下 {corpus.themes.length} 类主题分布。
        </p>
        <div className="theme-grid">
          {themes.map(([id, title, desc]) => (
            <div className="theme-item" key={id}>
              <div>
                <h3>
                  {title}{' '}
                  <span className="theme-count">
                    {corpus.themes.find((theme) => theme.id === id)
                      ?.instanceCount ?? '—'}{' '}
                    个任务
                  </span>
                </h3>
                <p>{desc}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}
