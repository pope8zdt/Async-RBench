import Link from 'next/link';
import { Leaderboard } from '@/components/leaderboard';
import { T } from '@/components/preferences';
export default function Home() {
  return (
    <div className="page-wrap">
      <section className="home-hero">
        <h1>Async-RBench</h1>
        <p>
          <T
            zh="201个高质量任务，评测异步执行与动态重规划能力。"
            en="201 high-quality tasks for evaluating asynchronous execution and dynamic replanning."
          />
        </p>
        <div className="actions">
          <Link href="/evaluate" className="btn primary">
            <T zh="开始评测" en="Run the benchmark" /> ↗
          </Link>
          <Link href="/tasks" className="btn secondary">
            <T zh="浏览任务" en="Explore tasks" /> ↗
          </Link>
        </div>
      </section>
      <section className="home-results" aria-labelledby="home-leaderboard-title">
        <h2 id="home-leaderboard-title" className="sr-only">
          <T zh="榜单" en="Leaderboard" />
        </h2>
        <Leaderboard />
      </section>
    </div>
  );
}
