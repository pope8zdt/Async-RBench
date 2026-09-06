'use client';
import { assetPath } from '@/lib/asset-path';
import Link from 'next/link';
import { useMemo, useState } from 'react';
import {
  ArrowDown,
  ArrowUpRight,
  Download,
  FlaskConical,
  ShieldCheck,
} from 'lucide-react';
import { Tabs, TabsList, TabsTrigger, TabsContent } from '@/components/ui/tabs';
import {
  Table,
  TableHeader,
  TableHead,
  TableBody,
  TableRow,
  TableCell,
} from '@/components/ui/table';
import {
  Select,
  SelectTrigger,
  SelectValue,
  SelectContent,
  SelectItem,
} from '@/components/ui/select';
import data from '@/public/data/experiments.json';
import { score, type Experiment } from '@/lib/content';
export function Leaderboard() {
  const [query, setQuery] = useState('');
  const [split, setSplit] = useState('all');
  const [page, setPage] = useState(0);
  const [sort, setSort] = useState<'date' | 'drs'>('date');
  const records = useMemo(
    () =>
      data.records
        .filter(
          (r) =>
            r.model.toLowerCase().includes(query.toLowerCase()) &&
            (split === 'all' || r.splits.includes(split)),
        )
        .sort((a, b) =>
          sort === 'drs'
            ? (b.drs ?? -1) - (a.drs ?? -1)
            : b.date.localeCompare(a.date),
        ),
    [query, split, sort],
  );
  const pageCount = Math.max(1, Math.ceil(records.length / 10));
  const safePage = Math.min(page, pageCount - 1);
  function table(rows: Experiment[]) {
    return (
      <div className="table-panel">
        <Table className="data-table">
          <TableHeader>
            <TableRow>
              <TableHead>模型 / 结果快照</TableHead>
              <TableHead>数据划分</TableHead>
              <TableHead>Linear BTS</TableHead>
              <TableHead>Async BTS</TableHead>
              <TableHead>
                <button
                  className="sort-button"
                  onClick={() => {
                    setSort(sort === 'drs' ? 'date' : 'drs');
                    setPage(0);
                  }}
                >
                  Async DRS <ArrowDown size={13} />
                </button>
              </TableHead>
              <TableHead>已评分 / Episodes</TableHead>
              <TableHead>详情</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.id}>
                <TableCell className="model-cell">
                  {r.model}
                  <small className="mono">
                    {r.id.slice(0, 8)} · {r.date.slice(0, 10)}
                  </small>
                </TableCell>
                <TableCell>
                  <span className="tag">{r.splits.join(' / ')}</span>
                </TableCell>
                <TableCell className="number">{score(r.linear)}</TableCell>
                <TableCell className="number">{score(r.async)}</TableCell>
                <TableCell className="number score-strong">
                  {score(r.drs)}
                </TableCell>
                <TableCell className="number">
                  {r.scored} / {r.episodes}
                </TableCell>
                <TableCell>
                  <Link
                    href={'/runs/' + r.id}
                    aria-label={'查看 ' + r.model + ' 运行详情'}
                  >
                    <ArrowUpRight size={17} />
                  </Link>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
        {rows.length === 0 && (
          <div className="empty-state">
            <p>没有符合条件的记录，请调整搜索或筛选条件。</p>
          </div>
        )}
        <div className="pagination-row">
          <span>
            {records.length} 条快照 · {safePage + 1} / {pageCount} 页
          </span>
          <div className="actions" style={{ margin: 0 }}>
            <button
              className="btn secondary"
              disabled={safePage === 0}
              onClick={() => setPage(safePage - 1)}
            >
              上一页
            </button>
            <button
              className="btn secondary"
              disabled={safePage >= pageCount - 1}
              onClick={() => setPage(safePage + 1)}
            >
              下一页
            </button>
          </div>
        </div>
      </div>
    );
  }
  return (
    <>
      <Tabs defaultValue="a">
        <TabsList className="tab-list">
          <TabsTrigger className="tab-trigger" value="a">
            Track A · 模型
          </TabsTrigger>
          <TabsTrigger className="tab-trigger" value="b">
            Track B · 系统预览
          </TabsTrigger>
        </TabsList>
        <TabsContent value="a" className="tab-content">
          <div className="section-heading">
            <div>
              <h2>实验记录</h2>
              <p className="muted" style={{ fontSize: 14, marginTop: 5 }}>
                独立批次的真实结果，尚未发布为正式榜单。
              </p>
            </div>
            <a
              href={assetPath('/data/experiments.json')}
              download
              className="text-link"
            >
              <Download size={15} /> 下载数据
            </a>
          </div>
          <div className="note amber">
            <FlaskConical size={18} />
            <span>
              不同快照的案例集合与覆盖率不同，不能直接作为统一排名。分数以 0–100
              展示；“—”表示没有可用评分，并非 0 分。模型名称按运行记录原样保留。
            </span>
          </div>
          <div className="toolbar">
            <label>
              <span className="screen-reader-only">搜索模型</span>
              <input
                className="search-input"
                value={query}
                placeholder="搜索模型名称…"
                onChange={(e) => {
                  setQuery(e.target.value);
                  setPage(0);
                }}
              />
            </label>
            <Select
              value={split}
              onValueChange={(v) => {
                setSplit(v ?? 'all');
                setPage(0);
              }}
            >
              <SelectTrigger
                className="select-trigger"
                aria-label="筛选数据划分"
              >
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                {[
                  ['all', '所有数据划分'],
                  ['calibration', 'Calibration'],
                  ['development', 'Development'],
                  ['test', 'Test'],
                ].map(([v, l]) => (
                  <SelectItem value={v} key={v}>
                    {l}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
            <span
              className="muted"
              style={{ fontSize: 12, marginLeft: 'auto' }}
            >
              快照更新于 {data.generatedAt.slice(0, 10)} UTC
            </span>
          </div>
          {table(
            records.slice(safePage * 10, safePage * 10 + 10) as Experiment[],
          )}
          <div className="panel" style={{ marginTop: 24 }}>
            <div style={{ display: 'flex', gap: 12, alignItems: 'center' }}>
              <ShieldCheck size={21} />
              <h3 style={{ fontSize: 18 }}>正式榜单 · 等待验证发布</h3>
            </div>
            <p className="muted" style={{ fontSize: 14, marginTop: 10 }}>
              满足冻结合约、完整配对和规定主题覆盖要求，并完成发布审核后，结果才进入正式榜单。本页面未将批次内的
              leaderboard 字段直接视为公开上榜资格。
            </p>
          </div>
        </TabsContent>
        <TabsContent value="b" className="tab-content">
          <div className="panel empty-state">
            <FlaskConical size={38} />
            <span className="tag">模拟预览</span>
            <h3 style={{ marginTop: 15 }}>Agent System Leaderboard</h3>
            <p>
              Track B
              尚未运行真实测评，也没有真实排名。现在可以预览框架选择、自定义组件与模拟运行流程。
            </p>
            <Link href="/evaluate?track=b" className="btn primary">
              预览 Track B <ArrowUpRight size={16} />
            </Link>
          </div>
        </TabsContent>
      </Tabs>
    </>
  );
}
