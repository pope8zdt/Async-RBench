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
import { score } from '@/lib/content';
import data from '@/public/data/experiments.json';

export function Leaderboard() {
  const [query, setQuery] = useState('');
  const records = useMemo(
    () =>
      data.records.filter((r) =>
        r.model.toLowerCase().includes(query.toLowerCase()),
      ),
    [query],
  );
  function metric(final: number | null, observed: number | null) {
    return final !== null ? (
      <span>{score(final)}</span>
    ) : (
      <span>
        {score(observed)}
        <small
          style={{
            display: 'block',
            fontSize: 12,
            color: 'var(--muted-foreground)',
          }}
        >
          暂计
        </small>
      </span>
    );
  }
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
              Linear / Async × 每种模式 3 次重复 · 每模型 282 次运行
            </p>
          </div>
          <a
            href={assetPath('/data/experiments.json')}
            download
            className="text-link"
          >
            <Download size={15} /> 下载主实验数据
          </a>
        </div>
        <div className="note">
          <span>
            暂计分数仅包含已完成的 case，不代表完整 47-case 成绩。缺失结果不计为
            0；分数范围为 0–100。
          </span>
        </div>
        <div className="toolbar">
          <label>
            <span className="screen-reader-only">搜索模型</span>
            <input
              className="search-input"
              placeholder="搜索主实验模型…"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
            />
          </label>
          <span className="muted" style={{ fontSize: 12, marginLeft: 'auto' }}>
            数据更新于 {data.generatedAt.slice(0, 10)} UTC
          </span>
        </div>
        <div className="table-panel">
          <Table className="data-table">
            <TableHeader>
              <TableRow>
                <TableHead>模型</TableHead>
                <TableHead>完成 Case</TableHead>
                <TableHead>Linear BTS</TableHead>
                <TableHead>Async BTS</TableHead>
                <TableHead>Async DRS</TableHead>
                <TableHead>已评分 / 计划运行</TableHead>
                <TableHead>状态 / 详情</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {records.map((r) => (
                <TableRow key={r.id}>
                  <TableCell className="model-cell">
                    {r.model}
                    <small className="mono">
                      {r.date?.slice(0, 10) ?? '尚无评分'}
                    </small>
                  </TableCell>
                  <TableCell className="number">
                    {r.completedCases} / {r.caseCount}
                  </TableCell>
                  <TableCell className="number">
                    {metric(r.linear, r.observedLinear)}
                  </TableCell>
                  <TableCell className="number">
                    {metric(r.async, r.observedAsync)}
                  </TableCell>
                  <TableCell className="number score-strong">
                    {metric(r.drs, r.observedDrs)}
                  </TableCell>
                  <TableCell className="number">
                    {r.scored} / {r.episodes}
                  </TableCell>
                  <TableCell>
                    <Link className="text-link" href={'/runs/' + r.id}>
                      {r.pairedComplete ? '完整统计' : '进行中'}{' '}
                      <ArrowUpRight size={16} />
                    </Link>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
          {records.length === 0 && (
            <div className="empty-state">没有匹配的主实验模型。</div>
          )}
        </div>
        <p className="muted" style={{ fontSize: 14, marginTop: 22 }}>
          三次重复先按 case
          平均，再对八类事件主题等权汇总。当前为实验记录，尚未独立复现。
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
