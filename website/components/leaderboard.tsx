'use client';
import { useMemo, useState } from 'react';
import Link from 'next/link';
import { ArrowUpRight, Download } from 'lucide-react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
  Table,
  TableHeader,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
} from '@/components/ui/table';
import { useCopy } from '@/components/preferences';
import { ReviewLabel } from '@/components/result-labels';
import { assetPath } from '@/lib/asset-path';
import { score, type Experiment } from '@/lib/content';
import {
  leaderboardRows,
  metricValue,
  reviewStatus,
  type MetricKey,
} from '@/lib/leaderboard.mjs';
import data from '@/public/data/leaderboard.json';

export function Leaderboard() {
  const copy = useCopy();
  const [query, setQuery] = useState('');
  const [view, setView] = useState<'bts' | 'drs'>('bts');
  const [btsSort, setBtsSort] = useState<'linear' | 'async'>('async');
  const sort: MetricKey = view === 'bts' ? btsSort : 'drs';
  const rows = useMemo(
    () => leaderboardRows(data.records as Experiment[], sort, query),
    [query, sort],
  );
  const columns: MetricKey[] = view === 'bts' ? ['linear', 'async'] : ['drs'];
  const titles = { linear: 'Linear BTS', async: 'Async BTS', drs: 'Async DRS' };
  const groups = [
    copy('正式排名 · 完整覆盖且已审核', 'Ranked · complete and reviewed'),
    copy('完整覆盖 · 未排名', 'Complete · unranked'),
    copy('暂计结果 · 覆盖不完整', 'Provisional · incomplete coverage'),
  ];
  return (
    <Tabs defaultValue="a">
      <TabsList className="tab-list">
        <TabsTrigger className="tab-trigger" value="a">
          {copy('Track A · 模型', 'Track A · Models')}
        </TabsTrigger>
        <TabsTrigger className="tab-trigger" value="b">
          {copy('Track B · 系统', 'Track B · Systems')}
        </TabsTrigger>
      </TabsList>
      <TabsContent value="a" className="tab-content">
        <div className="section-heading">
          <fieldset className="metric-switch">
            <legend className="screen-reader-only">
              {copy('指标', 'Metric')}
            </legend>
            <button
              type="button"
              aria-pressed={view === 'bts'}
              onClick={() => setView('bts')}
            >
              BTS
            </button>
            <button
              type="button"
              aria-pressed={view === 'drs'}
              onClick={() => setView('drs')}
            >
              DRS
            </button>
          </fieldset>
          <a
            href={assetPath('/data/leaderboard.json')}
            download
            className="text-link"
          >
            <Download size={15} /> {copy('下载数据', 'Download data')}
          </a>
        </div>
        <div className="toolbar">
          <label>
            <span className="screen-reader-only">
              {copy('搜索模型或记录', 'Search models or records')}
            </span>
            <input
              className="search-input"
              placeholder={copy('搜索模型…', 'Search models…')}
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          {view === 'bts' ? (
            <label className="sort-control">
              {copy('排序', 'Sort')}
              <select
                value={btsSort}
                onChange={(e) =>
                  setBtsSort(e.target.value as 'linear' | 'async')
                }
              >
                <option value="async">Async BTS ↓</option>
                <option value="linear">Linear BTS ↓</option>
              </select>
            </label>
          ) : (
            <span className="sort-control">Async DRS ↓</span>
          )}
        </div>
        <div className="table-panel">
          <Table className="data-table">
            <caption className="screen-reader-only">
              {copy(
                `主实验，按 ${titles[sort]} 降序，按覆盖与审核状态分组。`,
                `Main experiment, sorted by ${titles[sort]} descending and grouped by coverage and review status.`,
              )}
            </caption>
            <TableHeader>
              <TableRow>
                <TableHead>{copy('名次', 'Rank')}</TableHead>
                <TableHead>{copy('模型', 'Model')}</TableHead>
                {columns.map((key) => (
                  <TableHead
                    key={key}
                    aria-sort={key === sort ? 'descending' : undefined}
                  >
                    {titles[key]}
                  </TableHead>
                ))}
                <TableHead>{copy('配对覆盖', 'Paired coverage')}</TableHead>
                <TableHead>{copy('审核', 'Review')}</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map(({ record: r, rank, group }, index) => (
                <RecordRows
                  key={r.id}
                  record={r}
                  rank={rank}
                  columns={columns}
                  groupLabel={
                    index === 0 || rows[index - 1].group !== group
                      ? groups[group]
                      : null
                  }
                />
              ))}
            </TableBody>
          </Table>
          {rows.length === 0 && (
            <div className="empty-state">
              {copy('没有匹配的模型。', 'No matching models.')}
            </div>
          )}
        </div>
        <details className="section leaderboard-method">
          <summary>{copy('评分与排名规则', 'Scoring and ranking')}</summary>
          <p>
            {copy(
              'BTS 衡量任务完成质量，DRS 衡量异步重规划质量，均为 0–100 分。每种执行模式重复三次，先按任务平均，再对八类主题等权汇总。',
              'BTS measures task completion; DRS measures asynchronous replanning. Both use a 0–100 scale. Three repetitions per mode are averaged by task, then equally across eight themes.',
            )}
          </p>
          <p>
            {copy(
              '正式排名要求完整覆盖且材料已审核或已独立复现。材料审核不等于独立复现。暂计结果仅来自已完整评分任务，缺失值不计为零。搜索保留全榜名次。',
              'Ranking requires complete coverage and materials review or independent reproduction. Materials review is distinct from reproduction. Provisional scores use fully scored tasks only; missing values are not zeros. Search preserves overall ranks.',
            )}
          </p>
          <p>
            {copy('数据快照', 'Snapshot')}:{' '}
            {data.generatedAt.replace('T', ' ').slice(0, 19)} UTC
          </p>
        </details>
      </TabsContent>
      <TabsContent value="b" className="tab-content">
        <div className="panel empty-state">
          <span className="tag">{copy('模拟预览', 'Simulation preview')}</span>
          <h3 style={{ marginTop: 15 }}>
            {copy('Agent 系统榜单', 'Agent system leaderboard')}
          </h3>
          <p>
            {copy(
              '尚未开展真实测评，暂无排名。',
              'No live evaluations or rankings yet.',
            )}
          </p>
          <Link href="/evaluate?track=b" className="btn primary">
            {copy('预览 Track B', 'Preview Track B')} <ArrowUpRight size={16} />
          </Link>
        </div>
      </TabsContent>
    </Tabs>
  );
}

function RecordRows({
  record: r,
  rank,
  columns,
  groupLabel,
}: {
  record: Experiment;
  rank: number | null;
  columns: MetricKey[];
  groupLabel: string | null;
}) {
  return (
    <>
      {groupLabel && (
        <TableRow className="record-group">
          <TableCell colSpan={4 + columns.length}>{groupLabel}</TableCell>
        </TableRow>
      )}
      <TableRow>
        <TableCell className="number">{rank ?? '—'}</TableCell>
        <TableCell className="model-cell">
          <Link className="text-link" href={'/runs/' + r.id}>
            {r.model} <ArrowUpRight size={14} />
          </Link>
        </TableCell>
        {columns.map((key) => (
          <TableCell className="number" key={key}>
            {score(metricValue(r, key))}
          </TableCell>
        ))}
        <TableCell className="number">
          {((r.completedCases / r.caseCount) * 100).toFixed(1)}%
        </TableCell>
        <TableCell>
          <span className="status-label">
            <ReviewLabel status={reviewStatus(r)} />
          </span>
        </TableCell>
      </TableRow>
    </>
  );
}
