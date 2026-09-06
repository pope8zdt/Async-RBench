import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ArrowLeft, Download, FileCheck2 } from 'lucide-react';
import data from '@/public/data/experiments.json';
import { metrics, score, themes, type Experiment } from '@/lib/content';
import { assetPath } from '@/lib/asset-path';
export const metadata = { title: '主实验详情' };
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
        <ArrowLeft size={15} /> 返回主实验榜单
      </Link>
      <div className="page-title" style={{ marginTop: 25 }}>
        <div className="eyebrow">MAIN EXPERIMENT / FORMAL-47</div>
        <h1>{r.model}</h1>
        <p>
          固定 47 case · {r.date?.slice(0, 10) ?? '尚无评分'} ·{' '}
          {r.completedCases}/47 case 完整评分
        </p>
      </div>
      <div className="note amber">
        <FileCheck2 size={18} />
        <span>
          {r.pairedComplete
            ? '47 个 case 的配对与重复评分已齐备。该统计尚未声明通过独立复现。'
            : '运行仍在进行。下方为已完整评分 case 的暂计值，尚不是完整 47-case 得分。缺失评分不按 0 分处理。'}
        </span>
      </div>
      <div className="detail-grid">
        {metrics.map((m, i) => (
          <div className="detail-metric" key={m.name}>
            <span>
              {m.name}
              {r.pairedComplete ? '' : ' · 暂计'}
            </span>
            <strong>
              {score([r.observedLinear, r.observedAsync, r.observedDrs][i])}
            </strong>
            <span>{m.full} / 0–100</span>
          </div>
        ))}
      </div>
      <div className="panel">
        <h3 style={{ fontSize: 19 }}>主实验覆盖</h3>
        <div className="detail-facts">
          {[
            ['统计范围', '固定 47 case'],
            ['重复次数', 'Linear / Async 各 3 次'],
            ['完成 Case', `${r.completedCases} / 47`],
            ['已评分运行', `${r.scored} / ${r.episodes}`],
            ['暂计值覆盖主题', `${r.themeCount} / 8`],
            ['完整 47-case 得分', r.pairedComplete ? '已齐备' : '等待其余运行'],
            ['评测版本', r.version],
            ['发布验证', '待审核 / 未声明独立复现'],
          ].map(([label, value]) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
      </div>
      <section className="section">
        <h2>事件主题结果{r.pairedComplete ? '' : ' · 暂计'}</h2>
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
        <h3 style={{ fontSize: 19 }}>清单与结果来源</h3>
        <p className="muted" style={{ fontSize: 14, margin: '12px 0' }}>
          统计直接读取主实验 manifest 绑定的
          score.json，仅纳入固定清单中的实例。历史 split
          标签不参与筛选。先平均三次重复，再对 case、主题逐层聚合。
        </p>
        <p className="hash mono">
          清单 SHA-256 / {data.cohort.selection_sha256}
        </p>
        <p className="hash mono">来源集合 SHA-256 / {r.sourceSha256}</p>
        <p className="muted" style={{ fontSize: 14, margin: '12px 0' }}>
          来源集合摘要由清单摘要及已读取
          manifest、评分文件的摘要计算，用于追溯快照，不构成真实性认证。公开数据仅包含汇总指标。
        </p>
        <a
          className="text-link"
          download
          href={assetPath('/data/experiments.json')}
        >
          <Download size={15} /> 下载主实验公开统计
        </a>
      </section>
    </div>
  );
}
