'use client';

import { useEffect, useMemo, useState } from 'react';
import {
  Pause,
  Play,
  RotateCcw,
  SkipBack,
  SkipForward,
  Upload,
} from 'lucide-react';
import { useCopy } from '@/components/preferences';
import { eventDetails, parseScore, parseTrace } from '@/lib/trajectory.mjs';

type TraceEvent = Record<string, unknown> & {
  type: string;
  seq?: number;
  actor?: string;
  elapsed_ms?: number;
};
type ScoreSummary = Record<string, unknown> & {
  execution_mode?: string;
  score_status?: string;
  base_task_score?: number;
  async_drs?: number;
};

const demoEvents: TraceEvent[] = [
  { seq: 1, type: 'episode_started', actor: 'benchmark', elapsed_ms: 0 },
  {
    seq: 2,
    type: 'child_spawned',
    actor: 'adapter',
    child_id: 'child-1',
    workstream_id: 'inspect',
    elapsed_ms: 420,
  },
  {
    seq: 3,
    type: 'child_spawned',
    actor: 'adapter',
    child_id: 'child-2',
    workstream_id: 'verify',
    elapsed_ms: 610,
  },
  {
    seq: 4,
    type: 'child_completed',
    actor: 'adapter',
    child_id: 'child-2',
    workstream_id: 'verify',
    elapsed_ms: 5400,
  },
  {
    seq: 5,
    type: 'result_delivered',
    actor: 'benchmark',
    child_id: 'child-2',
    delivery_id: 'delivery-1',
    elapsed_ms: 6100,
  },
  {
    seq: 6,
    type: 'result_accepted',
    actor: 'adapter',
    child_id: 'child-2',
    result_id: 'result-1',
    elapsed_ms: 6900,
  },
  {
    seq: 7,
    type: 'child_completed',
    actor: 'adapter',
    child_id: 'child-1',
    workstream_id: 'inspect',
    elapsed_ms: 8800,
  },
  {
    seq: 8,
    type: 'episode_completed',
    actor: 'benchmark',
    status: 'scored',
    elapsed_ms: 12100,
  },
];
const demoScore: ScoreSummary = {
  episode_id: 'demo-async',
  execution_mode: 'async',
  score_status: 'scored',
  base_task_score: 0.76,
  async_drs: 0.68,
};

const labels: Record<string, [string, string]> = {
  episode_started: ['任务开始', 'Episode started'],
  child_spawned: ['启动子任务', 'Child spawned'],
  child_started: ['子任务运行', 'Child started'],
  child_completed: ['子任务完成', 'Child completed'],
  result_delivered: ['结果到达', 'Result delivered'],
  result_accepted: ['接受结果', 'Result accepted'],
  result_rejected: ['拒绝结果', 'Result rejected'],
  child_cancelled: ['取消子任务', 'Child cancelled'],
  episode_completed: ['任务结束', 'Episode completed'],
};

export function TrajectoryVisualizer() {
  const copy = useCopy();
  const [events, setEvents] = useState<TraceEvent[]>(demoEvents);
  const [score, setScore] = useState<ScoreSummary>(demoScore);
  const [active, setActive] = useState(0);
  const [playing, setPlaying] = useState(false);
  const [source, setSource] = useState(copy('示例轨迹', 'Demo trajectory'));
  const [error, setError] = useState('');

  useEffect(() => {
    if (!playing) return;
    const timer = window.setInterval(() => {
      setActive((current) => {
        if (current >= events.length - 1) {
          setPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, 1000);
    return () => window.clearInterval(timer);
  }, [events.length, playing]);

  const current = events[active] ?? events[0];
  const details = useMemo(() => eventDetails(current ?? {}), [current]);
  const progress =
    events.length <= 1 ? 100 : (active / (events.length - 1)) * 100;

  async function loadTrace(file?: File) {
    if (!file) return;
    try {
      const parsed = parseTrace(await file.text()) as TraceEvent[];
      setEvents(parsed);
      setActive(0);
      setPlaying(false);
      setSource(file.name);
      setError('');
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : copy('无法读取轨迹。', 'Unable to read trajectory.'),
      );
    }
  }

  async function loadScore(file?: File) {
    if (!file) return;
    try {
      setScore(parseScore(await file.text()) as ScoreSummary);
      setError('');
    } catch (caught) {
      setError(
        caught instanceof Error
          ? caught.message
          : copy('无法读取分数。', 'Unable to read score.'),
      );
    }
  }

  return (
    <div className="trajectory-viewer">
      <div className="trajectory-toolbar">
        <div>
          <span className="eyebrow">{copy('本地回放', 'Local replay')}</span>
          <strong>{source}</strong>
        </div>
        <div className="trajectory-files">
          <label className="btn secondary file-button">
            <Upload size={15} /> {copy('打开轨迹', 'Open trace')}
            <input
              type="file"
              accept=".jsonl,application/json"
              onChange={(event) => loadTrace(event.target.files?.[0])}
            />
          </label>
          <label className="btn secondary file-button">
            <Upload size={15} /> {copy('打开分数', 'Open score')}
            <input
              type="file"
              accept=".json,application/json"
              onChange={(event) => loadScore(event.target.files?.[0])}
            />
          </label>
        </div>
      </div>

      {error && (
        <p className="trajectory-error" role="alert">
          {error}
        </p>
      )}

      <div className="trajectory-stage">
        <aside
          className="trajectory-events"
          aria-label={copy('轨迹事件', 'Trajectory events')}
        >
          {events.map((event, index) => (
            <button
              type="button"
              aria-label={`${labels[event.type] ? copy(...labels[event.type]) : event.type}, ${formatTime(event.elapsed_ms)}`}
              key={`${event.seq ?? index}-${event.type}`}
              className={
                index === active
                  ? 'trajectory-event active'
                  : 'trajectory-event'
              }
              onClick={() => {
                setActive(index);
                setPlaying(false);
              }}
            >
              <span className="trajectory-dot" />
              <span>
                <strong>
                  {labels[event.type]
                    ? copy(...labels[event.type])
                    : event.type}
                </strong>
                <small>
                  {formatTime(event.elapsed_ms)} · {String(event.actor ?? '—')}
                </small>
              </span>
            </button>
          ))}
        </aside>

        <section className="trajectory-inspector" aria-live="polite">
          <div className="trajectory-progress">
            <span style={{ width: `${progress}%` }} />
          </div>
          <span className="tag">
            {active + 1} / {events.length}
          </span>
          <h2>
            {labels[current.type]
              ? copy(...labels[current.type])
              : current.type}
          </h2>
          <dl className="trajectory-details">
            {Object.entries(details).map(([key, value]) => (
              <div key={key}>
                <dt>{key.replaceAll('_', ' ')}</dt>
                <dd>{String(value)}</dd>
              </div>
            ))}
          </dl>
          <div className="trajectory-controls">
            <button
              type="button"
              onClick={() => {
                setActive(0);
                setPlaying(false);
              }}
              aria-label={copy('回到开头', 'Restart')}
            >
              <RotateCcw size={18} />
            </button>
            <button
              type="button"
              onClick={() => setActive((value) => Math.max(0, value - 1))}
              aria-label={copy('上一步', 'Previous')}
            >
              <SkipBack size={18} />
            </button>
            <button
              type="button"
              className="play-button"
              onClick={() => setPlaying(!playing)}
              aria-label={
                playing ? copy('暂停', 'Pause') : copy('播放', 'Play')
              }
            >
              {playing ? <Pause size={19} /> : <Play size={19} />}
            </button>
            <button
              type="button"
              onClick={() =>
                setActive((value) => Math.min(events.length - 1, value + 1))
              }
              aria-label={copy('下一步', 'Next')}
            >
              <SkipForward size={18} />
            </button>
          </div>
        </section>

        <aside className="trajectory-score">
          <span className="eyebrow">{copy('结果摘要', 'Result summary')}</span>
          <ScoreFact
            label={copy('执行模式', 'Mode')}
            value={String(score.execution_mode ?? '—')}
          />
          <ScoreFact label="BTS" value={formatScore(score.base_task_score)} />
          <ScoreFact label="DRS" value={formatScore(score.async_drs)} />
          <ScoreFact
            label={copy('状态', 'Status')}
            value={String(score.score_status ?? '—')}
          />
        </aside>
      </div>
      <p className="trajectory-privacy">
        {copy(
          '文件仅在当前浏览器中解析，不会上传。界面隐藏任务指令、私有真值和验证器内部字段。',
          'Files are parsed only in this browser and are never uploaded. Task instructions, private truth and verifier internals are hidden.',
        )}
      </p>
    </div>
  );
}

function ScoreFact({ label, value }: { label: string; value: string }) {
  return (
    <div className="score-fact">
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  );
}

function formatScore(value: unknown) {
  return typeof value === 'number' ? `${(value * 100).toFixed(1)}` : '—';
}

function formatTime(value: unknown) {
  if (typeof value !== 'number') return '—';
  return value < 1000
    ? `${Math.round(value)} ms`
    : `${(value / 1000).toFixed(1)} s`;
}
