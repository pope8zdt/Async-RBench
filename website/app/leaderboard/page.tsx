import { Leaderboard } from '@/components/leaderboard';
export const metadata = { title: 'Leaderboard' };
export default function Page() {
  return (
    <div className="page-wrap">
      <div className="page-title">
        <h1>Leaderboard</h1>
        <p>只统计固定主实验清单中的 47 个 case，按模型展示结果与完成进度。</p>
      </div>
      <Leaderboard />
    </div>
  );
}
