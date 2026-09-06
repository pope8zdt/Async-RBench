import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ArrowLeft, Download, FileCheck2 } from 'lucide-react';
import data from '@/public/data/leaderboard.json';
import {
  metrics,
  score,
  themes,
  reviewLabels,
  executionLabels,
  type Experiment,
} from '@/lib/content';
import {
  coverageStatus,
  reviewStatus,
  executionStatus,
  metricValue,
  type MetricKey,
} from '@/lib/leaderboard.mjs';
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
  const complete = coverageStatus(r) === 'complete';
  const keys: MetricKey[] = ['linear', 'async', 'drs'];
  return (
    <div className="page-wrap">
      <Link className="text-link" href="/leaderboard">
        <ArrowLeft size={15} /> 返回主实验榜单
      </Link>
      <div className="page-title" style={{ marginTop: 25 }}>
        <div className="eyebrow">MAIN EXPERIMENT</div>
        <h1>{r.model}</h1>
        <p>
          {r.date?.slice(0, 10) ?? '尚无评分'} · 配对完成度{' '}
          {((r.completedCases / r.caseCount) * 100).toFixed(1)}%
        </p>
        <p className="hash mono">记录 / {r.id}</p>
      </div>
      <div className="note amber">
        <FileCheck2 size={18} />
        <span>
          {complete
            ? '配对与重复评分已齐备，覆盖完整主实验清单。'
            : '覆盖不完整。下方为已完整评分任务的暂计值，尚不是完整主实验得分。缺失评分不按 0 分处理。'}{' '}
          审核：{reviewLabels[reviewStatus(r)]}。执行状态：
          {executionLabels[executionStatus(r)]}。材料审核不等于独立复现。
        </span>
      </div>
      <div className="detail-grid">
        {metrics.map((metric, index) => (
          <div className="detail-metric" key={metric.name}>
            <span>
              {metric.name}
              {complete ? '' : ' · 暂计'}
            </span>
            <strong>{score(metricValue(r, keys[index]))}</strong>
            <span>{metric.full} / 0–100</span>
          </div>
        ))}
      </div>
      <div className="panel">
        <h3 style={{ fontSize: 19 }}>主实验覆盖与来源状态</h3>
        <div className="detail-facts">
          {[
            ['统计范围', '主实验任务清单'],
            ['重复次数', `Linear / Async 各 ${data.cohort.repetitions} 次`],
            [
              '配对完成度',
              `${((r.completedCases / r.caseCount) * 100).toFixed(1)}%`,
            ],
            ['评分进度', `${((r.scored / r.episodes) * 100).toFixed(1)}%`],
            ['已覆盖主题', `${r.themeCount} / ${themes.length}`],
            ['覆盖状态', complete ? '完整' : '不完整'],
            ['评测版本', r.version],
            ['审核状态', reviewLabels[reviewStatus(r)]],
            ['执行状态', executionLabels[executionStatus(r)]],
            ['快照时间 (UTC)', data.generatedAt.replace('T', ' ').slice(0, 19)],
          ].map(([label, value]) => (
            <div key={label}>
              <span>{label}</span>
              <strong>{value}</strong>
            </div>
          ))}
        </div>
      </div>
      <section className="section">
        <div className="section-heading">
          <h2>事件主题结果{complete ? '' : ' · 暂计'}</h2>
        </div>
        <div className="table-panel corpus-table-wrap">
          <table className="data-table theme-results">
            <caption className="screen-reader-only">
              事件主题的配对 BTS 与 Async DRS 分数，范围 0–100
            </caption>
            <thead>
              <tr>
                <th scope="col">事件主题</th>
                <th scope="col">配对完成度</th>
                <th scope="col">Linear BTS</th>
                <th scope="col">Async BTS</th>
                <th scope="col">Async DRS</th>
              </tr>
            </thead>
            <tbody>
              {themes.map(([key, title]) => {
                const theme = r.themeMetrics?.[key];
                return (
                  <tr key={key}>
                    <th scope="row">{title}</th>
                    <td className="number">
                      {theme
                        ? `${((theme.completedCases / theme.caseCount) * 100).toFixed(1)}%`
                        : '—'}
                    </td>
                    <td className="number">{score(theme?.linear)}</td>
                    <td className="number">{score(theme?.async)}</td>
                    <td className="number">
                      {score(theme ? theme.drs : r.themeScores[key])}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="section-footnote">
          每个主题仅汇总已完整评分的
          任务；覆盖不足时为暂计值。旧快照可能仅含主题 DRS，缺失 BTS
          与完成度显示为「—」。
        </p>
      </section>
      {r.resources && (
        <section className="section panel">
          <h3 style={{ fontSize: 19 }}>资源观测</h3>
          <div className="detail-facts">
            {(['linear', 'async'] as const).map((mode) => (
              <div key={mode}>
                <span>{mode === 'linear' ? 'Linear' : 'Async'}</span>
                <strong className="resource-values">
                  {r.resources?.[mode].tokens.mean == null
                    ? '—'
                    : Math.round(r.resources[mode].tokens.mean).toLocaleString(
                        'en-US',
                      )}{' '}
                  tokens / 运行
                  <small className="cell-note">
                    已观测 {r.resources?.[mode].tokens.measuredEpisodes} 次
                  </small>
                  {r.resources?.[mode].durationMs.mean == null
                    ? '—'
                    : (r.resources[mode].durationMs.mean / 1000).toFixed(
                        1,
                      )}{' '}
                  秒 / 运行
                  <small className="cell-note">
                    已观测 {r.resources?.[mode].durationMs.measuredEpisodes} 次
                  </small>
                </strong>
              </div>
            ))}
          </div>
          <p className="section-footnote">
            均值仅来自完整评分任务中有观测值的运行。未观测值不按 0
            计，不同记录的观测覆盖可能不同；这些数据不是费用估算。
          </p>
        </section>
      )}
      <section className="section panel">
        <h3 style={{ fontSize: 19 }}>清单与结果来源</h3>
        <p className="section-footnote">
          {r.submissionId
            ? '该记录来自参与者提交的汇总包，审核状态由与包摘要绑定的维护者记录提供。'
            : '该快照由主实验清单绑定的评分汇总生成，仅纳入清单中的任务。'}{' '}
          历史 split 标签不参与筛选。先平均三次重复，再对
          任务、主题逐层聚合。公开数据仅包含汇总指标和可公开的来源元数据。
        </p>
        <p className="hash mono">
          清单 SHA-256 / {data.cohort.selection_sha256}
        </p>
        <p className="hash mono">来源集合 SHA-256 / {r.sourceSha256}</p>
        {r.submissionId && (
          <p className="hash mono">提交摘要 / {r.submissionId}</p>
        )}
        {r.benchmarkCommit && (
          <p className="hash mono">Benchmark commit / {r.benchmarkCommit}</p>
        )}
        {r.configSha256 && (
          <p className="hash mono">配置 SHA-256 / {r.configSha256}</p>
        )}
        {r.reviewer && (
          <p className="section-footnote">
            审核记录：{r.reviewer} · {r.reviewedAt}
          </p>
        )}
        {r.reviewEvidenceUrl && (
          <p>
            <a className="text-link" href={r.reviewEvidenceUrl}>
              查看审核 / 复现记录 ↗
            </a>
          </p>
        )}
        <p className="section-footnote">
          摘要用于识别与追溯具体快照，本身不构成分数真实性认证。本地结构校验不等于材料审核或独立复现。
        </p>
        <a
          className="text-link"
          download
          href={assetPath('/data/leaderboard.json')}
        >
          <Download size={15} /> 下载主实验公开统计
        </a>
      </section>
    </div>
  );
}
