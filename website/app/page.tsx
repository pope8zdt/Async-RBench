import Link from 'next/link';
import { ArrowRight, GitBranch, PackageCheck, PlayCircle } from 'lucide-react';
import { BenchmarkOverview } from '@/components/benchmark-overview';
import { Leaderboard } from '@/components/leaderboard';
import { T } from '@/components/preferences';
export default function Home() {
  return (
    <div className="page-wrap">
      <section className="home-hero">
        <span className="eyebrow">ASYNC AGENT EVALUATION</span>
        <h1>Async-RBench</h1>
        <p>
          <T
            zh="评测 Agent 能否整合异步返回的结果，并在任务状态变化后正确重规划。"
            en="Measure whether agents integrate asynchronous results and replan correctly as task state changes."
          />
        </p>
        <div className="actions">
          <Link href="/evaluate" className="btn primary">
            <T zh="开始评测" en="Run the benchmark" /> <ArrowRight size={16} />
          </Link>
          <Link href="/leaderboard" className="btn secondary">
            <T zh="查看榜单" en="View leaderboard" />
          </Link>
          <Link href="/visualizer" className="text-link hero-text-link">
            <T zh="轨迹回放" en="Replay traces" /> ↗
          </Link>
        </div>
      </section>

      <section className="benchmark-facts" aria-label="Benchmark summary">
        <Fact value="201" zh="高质量任务" en="high-quality tasks" />
        <Fact value="Linear / Async" zh="配对执行" en="paired execution" />
        <Fact
          value="BTS + DRS"
          zh="任务与重规划指标"
          en="task and replanning metrics"
        />
        <Fact
          value="Track A / B"
          zh="模型与 Agent 系统"
          en="models and agent systems"
        />
      </section>

      <section className="home-section" aria-labelledby="overview-title">
        <div className="home-section-heading">
          <div>
            <span className="eyebrow">
              <T zh="评测总览" en="Evaluation overview" />
            </span>
            <h2 id="overview-title">
              <T zh="从任务到可验证结果" en="From task to verifiable result" />
            </h2>
          </div>
          <p>
            <T
              zh="内核固定调度、隔离、结果交付与评分；参与者只接入模型或 Agent 系统。"
              en="The kernel fixes scheduling, isolation, result delivery and scoring; participants connect a model or agent system."
            />
          </p>
        </div>
        <BenchmarkOverview />
      </section>

      <section className="home-section" aria-labelledby="tracks-title">
        <div className="home-section-heading compact">
          <div>
            <span className="eyebrow">
              <T zh="参与方式" en="Evaluation tracks" />
            </span>
            <h2 id="tracks-title">
              <T zh="选择接入层级" en="Choose an integration level" />
            </h2>
          </div>
        </div>
        <div className="home-track-grid">
          <article className="home-track-card">
            <span className="track-index">A</span>
            <div>
              <h3>
                <T zh="模型接口" en="Model API" />
              </h3>
              <p>
                <T
                  zh="使用参考执行框架，对比同一模型在 Linear 与 Async 条件下的表现。"
                  en="Use the reference runner to compare one model under paired Linear and Async conditions."
                />
              </p>
              <Link href="/evaluate?track=a" className="text-link">
                <T zh="生成运行配置" en="Generate a run config" /> ↗
              </Link>
            </div>
          </article>
          <article className="home-track-card">
            <span className="track-index">B</span>
            <div>
              <h3>
                <T zh="Agent 系统" en="Agent system" />
              </h3>
              <p>
                <T
                  zh="运行 Codex CLI、Claude Code、LangGraph、OpenAI Agents 或自定义 Harness。"
                  en="Run Codex CLI, Claude Code, LangGraph, OpenAI Agents or a custom harness."
                />
              </p>
              <Link href="/evaluate?track=b" className="text-link">
                <T zh="配置 Agent 系统" en="Configure an agent system" /> ↗
              </Link>
            </div>
          </article>
        </div>
      </section>

      <section
        className="home-section workflow-section"
        aria-labelledby="workflow-title"
      >
        <div className="home-section-heading compact">
          <div>
            <span className="eyebrow">
              <T zh="完整工作流" en="Complete workflow" />
            </span>
            <h2 id="workflow-title">
              <T zh="运行、检查、提交" en="Run, inspect, submit" />
            </h2>
          </div>
        </div>
        <div className="workflow-grid">
          <Workflow
            icon={<GitBranch />}
            number="01"
            zh="本地运行"
            en="Run locally"
            zhText="评测在参与者电脑的隔离环境中执行。"
            enText="Evaluations execute in isolated environments on the participant's computer."
            href="/evaluate"
          />
          <Workflow
            icon={<PlayCircle />}
            number="02"
            zh="回放轨迹"
            en="Replay traces"
            zhText="查看事件顺序、子任务状态和异步结果交付。"
            enText="Inspect event order, child status and asynchronous result delivery."
            href="/visualizer"
          />
          <Workflow
            icon={<PackageCheck />}
            number="03"
            zh="验证并提交"
            en="Validate and submit"
            zhText="只导出摘要绑定的公开结果包，再交由维护者审核。"
            enText="Export a digest-bound public result package for maintainer review."
            href="/docs#submission"
          />
        </div>
      </section>

      <section
        className="home-results"
        aria-labelledby="home-leaderboard-title"
      >
        <div className="home-section-heading">
          <div>
            <span className="eyebrow">
              <T zh="当前结果" en="Current results" />
            </span>
            <h2 id="home-leaderboard-title">
              <T zh="排行榜" en="Leaderboard" />
            </h2>
          </div>
          <Link href="/leaderboard" className="text-link">
            <T zh="打开完整榜单" en="Open full leaderboard" /> ↗
          </Link>
        </div>
        <Leaderboard />
      </section>
    </div>
  );
}

function Fact({ value, zh, en }: { value: string; zh: string; en: string }) {
  return (
    <div>
      <strong>{value}</strong>
      <span>
        <T zh={zh} en={en} />
      </span>
    </div>
  );
}

function Workflow({
  icon,
  number,
  zh,
  en,
  zhText,
  enText,
  href,
}: {
  icon: React.ReactNode;
  number: string;
  zh: string;
  en: string;
  zhText: string;
  enText: string;
  href: string;
}) {
  return (
    <article className="workflow-card">
      <div className="workflow-icon">
        {icon}
        <span>{number}</span>
      </div>
      <h3>
        <T zh={zh} en={en} />
      </h3>
      <p>
        <T zh={zhText} en={enText} />
      </p>
      <Link href={href} className="text-link">
        <T zh="打开" en="Open" /> ↗
      </Link>
    </article>
  );
}
