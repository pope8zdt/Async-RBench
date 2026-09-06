import { Leaderboard } from '@/components/leaderboard';
export const metadata = { title: 'Leaderboard' };
export default function Page() {
  return (
    <div className="page-wrap">
      <div className="page-title">
        <h1>Leaderboard</h1>
        <p>按模型展示主实验结果与评测进度，支持配对 BTS 与 DRS 切换。</p>
      </div>
      <Leaderboard />
    </div>
  );
}
