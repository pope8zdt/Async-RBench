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
import { assetPath } from '@/lib/asset-path';
import {
  score,
  reviewLabels,
  executionLabels,
  type Experiment,
} from '@/lib/content';
import {
  leaderboardRows,
  metricValue,
  reviewStatus,
  executionStatus,
  type MetricKey,
} from '@/lib/leaderboard.mjs';
import data from '@/public/data/leaderboard.json';

export function Leaderboard() {
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
    '完整覆盖 · 已审核',
    '完整覆盖 · 未列入正式排名',
    '覆盖不完整 · 暂计结果',
  ];
  return (
    <Tabs defaultValue="a">
      <TabsList className="tab-list">
        <TabsTrigger className="tab-trigger" value="a">
          Track A · 主实验
        </TabsTrigger>
        <TabsTrigger className="tab-trigger" value="b">
          Track B · 系统预览
        </TabsTrigger>
      </TabsList>
      <TabsContent value="a" className="tab-content">
        <div className="section-heading">
          <div>
            <h2>主实验结果</h2>
            <p className="muted" style={{ fontSize: 14, marginTop: 5 }}>
              固定 {data.cohort.case_count} cases · Linear / Async · 每种模式{' '}
              {data.cohort.repetitions} 次重复
            </p>
          </div>
          <a
            href={assetPath('/data/leaderboard.json')}
            download
            className="text-link"
          >
            <Download size={15} /> 下载公开数据
          </a>
        </div>
        <fieldset className="metric-switch">
          <legend className="screen-reader-only">指标视图</legend>
          <button
            type="button"
            aria-pressed={view === 'bts'}
            onClick={() => setView('bts')}
          >
            BTS · Linear / Async 配对
          </button>
          <button
            type="button"
            aria-pressed={view === 'drs'}
            onClick={() => setView('drs')}
          >
            DRS · Async 重规划
          </button>
        </fieldset>
        <p className="section-footnote">
          {view === 'bts'
            ? '并列比较相同任务在 Linear 与 Async 条件下的基础任务得分。'
            : '比较 Async 条件下的动态重规划得分。'}{' '}
          分数范围 0–100，分数越高越好。
        </p>
        <div className="note">
          <span>
            正式名次仅包含完整覆盖且材料已审核或已独立复现的记录；材料审核不等于独立复现。暂计值不代表完整{' '}
            {data.cohort.case_count}-case 成绩，缺失结果不计为 0。
          </span>
        </div>
        <div className="toolbar">
          <label>
            <span className="screen-reader-only">搜索模型或记录编号</span>
            <input
              className="search-input"
              placeholder="搜索模型或记录编号…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          {view === 'bts' ? (
            <label className="sort-control">
              排序
              <select
                value={btsSort}
                onChange={(e) =>
                  setBtsSort(e.target.value as 'linear' | 'async')
                }
              >
                <option value="async">Async BTS · 从高到低</option>
                <option value="linear">Linear BTS · 从高到低</option>
              </select>
            </label>
          ) : (
            <span className="muted" style={{ fontSize: 13 }}>
              Async DRS · 从高到低
            </span>
          )}
          <span className="snapshot-time">
            快照 {data.generatedAt.replace('T', ' ').slice(0, 19)} UTC
          </span>
        </div>
        <div className="table-panel">
          <Table className="data-table">
            <caption className="screen-reader-only">
              固定 {data.cohort.case_count} case 主实验；按 {titles[sort]}{' '}
              降序，各覆盖与审核组分开展示。
            </caption>
            <TableHeader>
              <TableRow>
                <TableHead>名次</TableHead>
                <TableHead>模型 / 记录</TableHead>
                <TableHead>完整评分 Case</TableHead>
                {columns.map((key) => (
                  <TableHead
                    key={key}
                    aria-sort={key === sort ? 'descending' : undefined}
                  >
                    {titles[key]}
                  </TableHead>
                ))}
                <TableHead>已评分 / 计划运行</TableHead>
                <TableHead>审核 / 执行状态</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.map(({ record: r, rank, group, complete }, index) => (
                <RecordRows
                  key={r.id}
                  record={r}
                  rank={rank}
                  complete={complete}
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
            <div className="empty-state">没有匹配的主实验记录。</div>
          )}
        </div>
        <p className="section-footnote">
          三次重复先按 case
          平均，再对八类事件主题等权汇总。完整记录与暂计记录分别排序；搜索保留全榜名次。执行状态仅按明确报告展示。
        </p>
      </TabsContent>
      <TabsContent value="b" className="tab-content">
        <div className="panel empty-state">
          <span className="tag">模拟预览</span>
          <h3 style={{ marginTop: 15 }}>Agent System Leaderboard</h3>
          <p>Track B 尚未运行真实测评，也没有真实排名。</p>
          <Link href="/evaluate?track=b" className="btn primary">
            预览 Track B <ArrowUpRight size={16} />
          </Link>
        </div>
      </TabsContent>
    </Tabs>
  );
}

function RecordRows({
  record: r,
  rank,
  complete,
  columns,
  groupLabel,
}: {
  record: Experiment;
  rank: number | null;
  complete: boolean;
  columns: MetricKey[];
  groupLabel: string | null;
}) {
  return (
    <>
      {groupLabel && (
        <TableRow className="record-group">
          <TableCell colSpan={5 + columns.length}>{groupLabel}</TableCell>
        </TableRow>
      )}
      <TableRow>
        <TableCell className="number">{rank ?? '—'}</TableCell>
        <TableCell className="model-cell">
          <Link className="text-link" href={'/runs/' + r.id}>
            {r.model} <ArrowUpRight size={14} />
          </Link>
          <small className="mono" title={r.id}>
            {r.id.slice(0, 12)} · {r.date?.slice(0, 10) ?? '尚无评分'}
          </small>
        </TableCell>
        <TableCell className="number">
          {r.completedCases} / {r.caseCount}
          <small className="cell-note">
            {complete ? '完整覆盖' : '覆盖不完整'}
          </small>
        </TableCell>
        {columns.map((key) => (
          <TableCell className="number" key={key}>
            {score(metricValue(r, key))}
            {!complete && metricValue(r, key) !== null && (
              <small className="cell-note">暂计</small>
            )}
          </TableCell>
        ))}
        <TableCell className="number">
          {r.scored} / {r.episodes}
        </TableCell>
        <TableCell>
          <span className="status-label">{reviewLabels[reviewStatus(r)]}</span>
          <small className="cell-note">
            执行：{executionLabels[executionStatus(r)]}
          </small>
        </TableCell>
      </TableRow>
    </>
  );
}
