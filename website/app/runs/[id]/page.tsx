import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ArrowLeft, Download, FileCheck2 } from 'lucide-react';
import data from '@/public/data/experiments.json';
import { metrics, score, themes, type Experiment } from '@/lib/content';
import { assetPath } from '@/lib/asset-path';
export const metadata = { title: '实验详情' };
export const dynamicParams = false;
export function generateStaticParams() {
  return data.records.map(({ id }) => ({ id }));
}
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const r = data.records.find((x) => x.id === id) as Experiment | undefined;
  if (!r) notFound();
  return (
    <div className="page-wrap">
      <Link className="text-link" href="/leaderboard">
        <ArrowLeft size={15} /> 返回实验记录
      </Link>
      <div className="page-title" style={{ marginTop: 25 }}>
        <div className="eyebrow">EXPERIMENT SNAPSHOT / {r.id.slice(0, 8)}</div>
        <h1>{r.model}</h1>
        <p>
          独立批次结果 · {r.date.slice(0, 10)} ·{' '}
          <span className="tag">未发布为正式榜单</span>
        </p>
      </div>
      <div className="note amber">
        <FileCheck2 size={18} />
        <span>
          以下数值直接来自此批次的 development_summary。它们不是完整 benchmark
          的模型得分，也没有与其他批次合并。
        </span>
      </div>
      <div className="detail-grid">
        {metrics.map((m, i) => (
          <div className="detail-metric" key={m.name}>
            <span>{m.name}</span>
            <strong>{score([r.linear, r.async, r.drs][i])}</strong>
            <span>{m.full} / 0–100</span>
          </div>
        ))}
      </div>
      <div className="panel">
        <h3 style={{ fontSize: 19 }}>运行事实</h3>
        <div className="detail-facts">
          <div>
            <span>结果记录版本</span>
            <strong>{r.version}</strong>
          </div>
          <div>
            <span>数据划分</span>
            <strong>{r.splits.join(' / ')}</strong>
          </div>
          <div>
            <span>已评分 episodes</span>
            <strong>
              {r.scored} / {r.episodes}
            </strong>
          </div>
          <div>
            <span>完整配对标记</span>
            <strong>{r.pairedComplete ? '是' : '否 / 未提供'}</strong>
          </div>
          <div>
            <span>DRS 结果覆盖主题</span>
            <strong>{r.themeCount} / 8</strong>
          </div>
          <div>
            <span>公开发布状态</span>
            <strong>待审核</strong>
          </div>
          <div>
            <span>Linear 平均耗时</span>
            <strong>
              {r.linearMs === null
                ? '—'
                : (r.linearMs / 1000).toFixed(1) + ' s'}
            </strong>
          </div>
          <div>
            <span>Async 平均耗时</span>
            <strong>
              {r.asyncMs === null ? '—' : (r.asyncMs / 1000).toFixed(1) + ' s'}
            </strong>
          </div>
        </div>
      </div>
      <section className="section">
        <h2>事件主题结果</h2>
        <div className="theme-grid">
          {themes.map(([key, title]) => (
            <div
              key={key}
              className="theme-item"
              style={{ justifyContent: 'space-between' }}
            >
              <h4>{title}</h4>
              <span className="number score-strong">
                {score(r.themeScores[key] ?? null)}
              </span>
            </div>
          ))}
        </div>
      </section>
      <section className="section panel">
        <h3 style={{ fontSize: 19 }}>来源与可复查性</h3>
        <p className="muted" style={{ fontSize: 14, margin: '12px 0' }}>
          来源类型：评测程序生成的
          results.json。下方摘要可用于与原文件比对；导出仅包含指标及统计信息，没有任务路径、密钥或私有轨迹。
        </p>
        <p className="hash mono">SHA-256 / {r.sourceSha256}</p>
        <p className="muted" style={{ fontSize: 14, margin: '15px 0' }}>
          轨迹回放：该批次尚未提供经公开审查的轨迹，当前不展示。
        </p>
        <a
          className="text-link"
          download
          href={assetPath('/data/experiments.json')}
        >
          <Download size={15} /> 下载全部公开字段快照
        </a>
      </section>
    </div>
  );
}
