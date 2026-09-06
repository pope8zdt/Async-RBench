import { Leaderboard } from '@/components/leaderboard';
export const metadata = { title: 'Leaderboard' };
export default function Page() {
  return (
    <div className="page-wrap">
      <div className="page-title">
        <div className="eyebrow">RESULTS & REPRODUCIBILITY</div>
        <h1>Leaderboard</h1>
        <p>从任务正确性、动态重规划和评测覆盖率，理解每一次运行的结果。</p>
      </div>
      <Leaderboard />
    </div>
  );
}
