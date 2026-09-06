import Link from 'next/link';
import { notFound } from 'next/navigation';
import { ArrowLeft, Download } from 'lucide-react';
import { T } from '@/components/preferences';
import {
  ReviewLabel,
  ExecutionLabel,
  ThemeLabel,
} from '@/components/result-labels';
import data from '@/public/data/leaderboard.json';
import { score, themes, type Experiment } from '@/lib/content';
import {
  coverageStatus,
  reviewStatus,
  executionStatus,
  metricValue,
  type MetricKey,
} from '@/lib/leaderboard.mjs';
import { assetPath } from '@/lib/asset-path';
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
  const metricTitles: Record<MetricKey, string> = {
    linear: 'Linear BTS',
    async: 'Async BTS',
    drs: 'Async DRS',
  };
  return (
    <div className="page-wrap">
      <Link className="text-link" href="/leaderboard">
        <ArrowLeft size={15} /> <T zh="排行榜" en="Leaderboard" />
      </Link>
      <div className="page-title" style={{ marginTop: 25 }}>
        <div className="eyebrow">
          <T zh="Track A · 模型评测" en="Track A · Model evaluation" />
        </div>
        <h1>{r.model}</h1>
        <p>
          {complete ? (
            <T zh="完整覆盖" en="Complete coverage" />
          ) : (
            <T
              zh="暂计结果 · 覆盖不完整"
              en="Provisional · incomplete coverage"
            />
          )}
          {' · '}
          <ReviewLabel status={reviewStatus(r)} />
        </p>
      </div>
      <div className="detail-grid">
        {(['linear', 'async', 'drs'] as const).map((key) => (
          <div className="detail-metric" key={key}>
            <span>{metricTitles[key]}</span>
            <strong>{score(metricValue(r, key))}</strong>
            <span>/ 100</span>
          </div>
        ))}
      </div>
      <div className="panel">
        <h2 style={{ fontSize: 19 }}>
          <T zh="评测覆盖" en="Evaluation coverage" />
        </h2>
        <div className="detail-facts">
          <div>
            <span>
              <T zh="配对覆盖" en="Paired coverage" />
            </span>
            <strong>
              {((r.completedCases / r.caseCount) * 100).toFixed(1)}%
            </strong>
          </div>
          <div>
            <span>
              <T zh="评分进度" en="Scoring progress" />
            </span>
            <strong>{((r.scored / r.episodes) * 100).toFixed(1)}%</strong>
          </div>
          <div>
            <span>
              <T zh="主题覆盖" en="Theme coverage" />
            </span>
            <strong>
              {((r.themeCount / themes.length) * 100).toFixed(1)}%
            </strong>
          </div>
          <div>
            <span>
              <T zh="执行状态" en="Execution status" />
            </span>
            <strong>
              <ExecutionLabel status={executionStatus(r)} />
            </strong>
          </div>
        </div>
      </div>
      <section className="section">
        <div className="section-heading">
          <h2>
            <T zh="主题得分" en="Scores by theme" />
          </h2>
        </div>
        <div className="table-panel corpus-table-wrap">
          <table className="data-table theme-results">
            <caption className="screen-reader-only">
              <T
                zh="各事件主题的配对覆盖与 BTS、DRS 得分，范围 0–100。"
                en="Paired coverage and BTS / DRS scores by event theme, on a 0–100 scale."
              />
            </caption>
            <thead>
              <tr>
                <th scope="col">
                  <T zh="事件主题" en="Event theme" />
                </th>
                <th scope="col">
                  <T zh="配对覆盖" en="Paired coverage" />
                </th>
                <th scope="col">Linear BTS</th>
                <th scope="col">Async BTS</th>
                <th scope="col">Async DRS</th>
              </tr>
            </thead>
            <tbody>
              {themes.map((entry) => {
                const key = entry[0];
                const theme = r.themeMetrics?.[key];
                return (
                  <tr key={key}>
                    <th scope="row">
                      <ThemeLabel theme={entry} />
                    </th>
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
      </section>
      {r.resources && (
        <details className="section panel">
          <summary>
            <T zh="资源观测" en="Resource observations" />
          </summary>
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
                  <T zh="tokens / 运行" en="tokens / run" />
                  <small className="cell-note">
                    <T
                      zh={`观测 ${r.resources?.[mode].tokens.measuredEpisodes} 次`}
                      en={`${r.resources?.[mode].tokens.measuredEpisodes} measured runs`}
                    />
                  </small>
                  {r.resources?.[mode].durationMs.mean == null
                    ? '—'
                    : (r.resources[mode].durationMs.mean / 1000).toFixed(
                        1,
                      )}{' '}
                  <T zh="秒 / 运行" en="seconds / run" />
                  <small className="cell-note">
                    <T
                      zh={`观测 ${r.resources?.[mode].durationMs.measuredEpisodes} 次`}
                      en={`${r.resources?.[mode].durationMs.measuredEpisodes} measured runs`}
                    />
                  </small>
                </strong>
              </div>
            ))}
          </div>
          <p>
            <T
              zh="均值仅含完整评分任务中有观测值的运行；缺失值不计为零。观测覆盖可能不同，数据不代表费用。"
              en="Means include measured runs from fully scored tasks only; missing values are not zeros. Observation coverage varies. These are not cost estimates."
            />
          </p>
        </details>
      )}
      <details className="section panel">
        <summary>
          <T zh="来源与审核" en="Sources and review" />
        </summary>
        <div className="detail-facts">
          <div>
            <span>
              <T zh="审核状态" en="Review status" />
            </span>
            <strong>
              <ReviewLabel status={reviewStatus(r)} />
            </strong>
          </div>
          <div>
            <span>
              <T zh="评测版本" en="Benchmark version" />
            </span>
            <strong>{r.version}</strong>
          </div>
          <div>
            <span>
              <T zh="重复次数" en="Repetitions" />
            </span>
            <strong>
              <T
                zh={`Linear / Async 各 ${data.cohort.repetitions} 次`}
                en={`${data.cohort.repetitions} each for Linear / Async`}
              />
            </strong>
          </div>
          <div>
            <span>
              <T zh="结果日期" en="Result date" />
            </span>
            <strong>
              {r.date?.slice(0, 10) ?? <T zh="尚无评分" en="Not yet scored" />}
            </strong>
          </div>
          <div>
            <span>
              <T zh="快照时间 (UTC)" en="Snapshot (UTC)" />
            </span>
            <strong>{data.generatedAt.replace('T', ' ').slice(0, 19)}</strong>
          </div>
        </div>
        <p>
          {r.submissionId ? (
            <T
              zh="参与者自行报告的汇总结果；审核状态来自与提交摘要绑定的维护者记录。"
              en="Participant self-reported aggregates; review status comes from a maintainer record bound to the submission digest."
            />
          ) : (
            <T
              zh="结果由固定主实验清单中的评分汇总生成。"
              en="Results are aggregated from the fixed main-experiment selection."
            />
          )}
        </p>
        <p>
          <T
            zh="仅汇总完整评分任务，先平均三次重复，再对任务和主题逐层聚合。覆盖不足时为暂计值，缺失值显示为 —，不计为零。"
            en="Only fully scored tasks are aggregated, averaging three repetitions before task and theme aggregation. Incomplete coverage produces provisional values. Missing values appear as — and are not zeros."
          />
        </p>
        <p>
          <T
            zh="材料审核与独立复现分别记录；摘要和结构校验不能认证分数真实性。"
            en="Materials review and independent reproduction are recorded separately. Digests and structural validation do not authenticate scores."
          />
        </p>
        <p className="hash mono">
          <T zh="记录" en="Record" /> / {r.id}
        </p>
        <p className="hash mono">
          <T zh="清单 SHA-256" en="Selection SHA-256" /> /{' '}
          {data.cohort.selection_sha256}
        </p>
        <p className="hash mono">
          <T zh="来源集合 SHA-256" en="Source set SHA-256" /> / {r.sourceSha256}
        </p>
        {r.submissionId && (
          <p className="hash mono">
            <T zh="提交摘要" en="Submission digest" /> / {r.submissionId}
          </p>
        )}
        {r.benchmarkCommit && (
          <p className="hash mono">
            <T zh="评测提交版本" en="Benchmark commit" /> / {r.benchmarkCommit}
          </p>
        )}
        {r.configSha256 && (
          <p className="hash mono">
            <T zh="配置 SHA-256" en="Configuration SHA-256" /> /{' '}
            {r.configSha256}
          </p>
        )}
        {r.reviewer && (
          <p>
            <T zh="审核记录" en="Review record" />: {r.reviewer} ·{' '}
            {r.reviewedAt}
          </p>
        )}
        {r.reviewEvidenceUrl && (
          <p>
            <a className="text-link" href={r.reviewEvidenceUrl}>
              <T
                zh="查看审核 / 复现记录 ↗"
                en="View review / reproduction evidence ↗"
              />
            </a>
          </p>
        )}
        <a
          className="text-link"
          download
          href={assetPath('/data/leaderboard.json')}
        >
          <Download size={15} /> <T zh="下载数据" en="Download data" />
        </a>
      </details>
    </div>
  );
}
