import { Leaderboard } from '@/components/leaderboard';
import { T } from '@/components/preferences';
export default function Page() {
  return (
    <div className="page-wrap">
      <div className="page-title">
        <h1>
          <T zh="排行榜" en="Leaderboard" />
        </h1>
      </div>
      <Leaderboard />
    </div>
  );
}
