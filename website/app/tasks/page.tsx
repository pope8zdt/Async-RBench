import corpus from '@/public/data/corpus.json';
import { themes } from '@/lib/content';
import { T } from '@/components/preferences';
import { assetPath } from '@/lib/asset-path';
const english = [
  'Late authoritative results',
  'Stale and out-of-order results',
  'Partial to complete results',
  'Conflicting results',
  'Duplicate and replayed results',
  'Child task failures',
  'Scope and dependency changes',
  'Stragglers under resource pressure',
];
export default function TasksPage() {
  const maximum = Math.max(
    1,
    ...corpus.themes.map((theme) => theme.instanceCount),
  );
  return (
    <div className="page-wrap">
      <div className="page-title">
        <h1>
          <T zh="任务" en="Tasks" />
        </h1>
        <p>
          <T
            zh="201个高质量任务，覆盖八类异步事件。"
            en="201 high-quality tasks across eight asynchronous event themes."
          />
        </p>
      </div>
      <div className="table-panel corpus-table-wrap">
        <table className="data-table corpus-table">
          <caption className="screen-reader-only">
            <T zh="任务主题分布" en="Task distribution by theme" />
          </caption>
          <thead>
            <tr>
              <th scope="col">
                <T zh="事件主题" en="Event theme" />
              </th>
              <th scope="col">
                <T zh="任务数量" en="Tasks" />
              </th>
              <th scope="col">
                <T zh="占比" en="Share" />
              </th>
            </tr>
          </thead>
          <tbody>
            {corpus.themes.map((theme) => {
              const index = themes.findIndex(([id]) => id === theme.id);
              return (
                <tr key={theme.id}>
                  <th scope="row">
                    <T
                      zh={themes[index]?.[1] ?? theme.id}
                      en={english[index] ?? theme.id}
                    />
                  </th>
                  <td className="number">
                    {theme.instanceCount}
                    <div className="corpus-bar" aria-hidden="true">
                      <span
                        style={{
                          width: `${(theme.instanceCount / maximum) * 100}%`,
                        }}
                      />
                    </div>
                  </td>
                  <td className="number">
                    {(
                      (theme.instanceCount / corpus.instanceCount) *
                      100
                    ).toFixed(1)}
                    %
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      <div className="actions">
        <a className="text-link" href={assetPath('/data/corpus.json')} download>
          <T zh="下载分布数据" en="Download distribution" /> ↓
        </a>
      </div>
    </div>
  );
}
