import Link from 'next/link';
import corpus from '@/public/data/corpus.json';
import data from '@/public/data/experiments.json';
import { themes } from '@/lib/content';
import { assetPath } from '@/lib/asset-path';

export const metadata = { title: '任务库与事件分布' };

export default function TasksPage() {
  const maximum = Math.max(1, ...corpus.themes.map((theme) => theme.caseCount));
  return (
    <div className="page-wrap">
      <div className="page-title">
        <div className="eyebrow">TASK CORPUS</div>
        <h1>任务库与事件分布</h1>
        <p>
          当前仓库包含 {corpus.caseCount} 个 case、{corpus.instanceCount}{' '}
          个注册实例，覆盖 {corpus.themes.length}{' '}
          类异步事件主题。数量由当前仓库注册表生成。
        </p>
      </div>
      <div className="note">
        <span>
          任务库描述覆盖完整仓库。公开主榜使用固定 {data.cohort.case_count}-case
          清单、Linear / Async 两种条件及每种模式 {data.cohort.repetitions}{' '}
          次重复；完整任务库总数不是主榜分母。
        </span>
      </div>
      <section className="section">
        <div className="section-heading">
          <h2>完整任务库分布</h2>
          <a
            className="text-link"
            href={assetPath('/data/corpus.json')}
            download
          >
            下载分布数据 ↗
          </a>
        </div>
        <div className="table-panel corpus-table-wrap">
          <table className="data-table corpus-table">
            <caption className="screen-reader-only">
              当前仓库各主题 case 数量、占比与注册实例数量
            </caption>
            <thead>
              <tr>
                <th scope="col">事件主题</th>
                <th scope="col">Cases / 占比</th>
                <th scope="col">注册实例</th>
              </tr>
            </thead>
            <tbody>
              {corpus.themes.map((theme) => {
                const description = themes.find(([id]) => id === theme.id);
                const share = corpus.caseCount
                  ? (theme.caseCount / corpus.caseCount) * 100
                  : 0;
                return (
                  <tr key={theme.id}>
                    <th scope="row">
                      <span>{description?.[1] ?? theme.id}</span>
                      <small className="cell-note">{description?.[2]}</small>
                    </th>
                    <td>
                      <span className="number">
                        {theme.caseCount}{' '}
                        <span className="muted">/ {share.toFixed(1)}%</span>
                      </span>
                      <div className="corpus-bar" aria-hidden="true">
                        <span
                          style={{
                            width: `${(theme.caseCount / maximum) * 100}%`,
                          }}
                        />
                      </div>
                    </td>
                    <td className="number">{theme.instanceCount}</td>
                  </tr>
                );
              })}
            </tbody>
            <tfoot>
              <tr>
                <th scope="row">总计</th>
                <td className="number">{corpus.caseCount} / 100%</td>
                <td className="number">{corpus.instanceCount}</td>
              </tr>
            </tfoot>
          </table>
        </div>
        <p className="section-footnote">
          Case 表示独立任务；注册实例表示注册表中的实例条目，同一 case
          可对应多个实例。图条按本表最大主题数量缩放，具体数量与占比见文字。
        </p>
      </section>
      <section className="section panel">
        <h3>快照与主实验范围</h3>
        <p className="section-footnote">
          任务库快照：{corpus.generatedAt.replace('T', ' ').slice(0, 19)}{' '}
          UTC。每次生成网站数据时重新读取仓库注册表。
        </p>
        <p className="hash mono">注册表 SHA-256 / {corpus.registrySha256}</p>
        <p className="section-footnote">
          固定 {data.cohort.case_count}-case 主实验使用独立的选择摘要。历史
          calibration / development / test 标签不决定主榜成员或分组。
        </p>
        <div className="actions">
          <Link className="text-link" href="/leaderboard">
            查看主榜 ↗
          </Link>
          <Link className="text-link" href="/docs#protocol">
            评测协议 ↗
          </Link>
        </div>
      </section>
    </div>
  );
}
