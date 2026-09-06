import Link from 'next/link';
export default function NotFound() {
  return (
    <div className="page-wrap empty-state">
      <h1>没有找到这条记录</h1>
      <p>该链接可能来自另一个结果快照版本。</p>
      <Link className="btn primary" href="/leaderboard">
        返回实验记录
      </Link>
    </div>
  );
}
