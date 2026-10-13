'use client';

import { useCopy } from '@/components/preferences';

export function BenchmarkOverview() {
  const copy = useCopy();
  return (
    <div className="benchmark-diagram">
      <svg
        viewBox="0 0 1120 560"
        aria-labelledby="benchmark-diagram-title benchmark-diagram-description"
      >
        <title id="benchmark-diagram-title">
          {copy(
            'Async-RBench 评测架构',
            'Async-RBench evaluation architecture',
          )}
        </title>
        <desc id="benchmark-diagram-description">
          {copy(
            '任务进入参与者 Agent，由评测内核调度隔离工作区、异步结果和验证，最终生成 BTS 与 DRS。',
            'Tasks enter the participant agent; the evaluation kernel coordinates isolated workspaces, asynchronous results and verification to produce BTS and DRS.',
          )}
        </desc>
        <defs>
          <marker
            id="overview-arrow"
            viewBox="0 0 10 10"
            refX="8"
            refY="5"
            markerWidth="7"
            markerHeight="7"
            orient="auto-start-reverse"
          >
            <path d="M 0 0 L 10 5 L 0 10 z" className="diagram-arrow-head" />
          </marker>
        </defs>

        <g className="diagram-node diagram-input">
          <rect x="28" y="142" width="210" height="222" rx="18" />
          <text x="52" y="180" className="diagram-title">
            {copy('任务集', 'Task suite')}
          </text>
          <text x="52" y="214" className="diagram-label">
            {copy('201个高质量任务', '201 high-quality tasks')}
          </text>
          <text x="52" y="244" className="diagram-label">
            {copy('主题覆盖', 'Theme coverage')}
          </text>
          <line x1="52" y1="268" x2="214" y2="268" />
          <text x="52" y="302" className="diagram-kicker">
            LINEAR
          </text>
          <text x="135" y="302" className="diagram-kicker">
            ASYNC
          </text>
          <text x="52" y="332" className="diagram-small">
            {copy(
              '同任务 · 同模型 · 配对运行',
              'Same task · model · paired runs',
            )}
          </text>
        </g>

        <g className="diagram-node diagram-agent">
          <rect x="344" y="34" width="430" height="104" rx="18" />
          <text x="370" y="72" className="diagram-title">
            {copy('参与者 Agent', 'Participant agent')}
          </text>
          <text x="370" y="105" className="diagram-label">
            Track A · API
          </text>
          <text x="548" y="105" className="diagram-label">
            Track B · Harness
          </text>
          <line x1="520" y1="82" x2="520" y2="116" />
        </g>

        <g className="diagram-node diagram-kernel">
          <rect x="302" y="210" width="514" height="236" rx="26" />
          <text x="330" y="250" className="diagram-title">
            {copy('Async-RBench 评测内核', 'Async-RBench evaluation kernel')}
          </text>
          <g className="diagram-module">
            <rect x="330" y="278" width="210" height="60" rx="12" />
            <text x="350" y="314" className="diagram-label">
              {copy('调度器', 'Scheduler')}
            </text>
          </g>
          <g className="diagram-module">
            <rect x="576" y="278" width="210" height="60" rx="12" />
            <text x="596" y="314" className="diagram-label">
              {copy('结果网关', 'Result gateway')}
            </text>
          </g>
          <g className="diagram-module">
            <rect x="330" y="358" width="210" height="60" rx="12" />
            <text x="350" y="394" className="diagram-label">
              {copy('事件与轨迹', 'Events & traces')}
            </text>
          </g>
          <g className="diagram-module">
            <rect x="576" y="358" width="210" height="60" rx="12" />
            <text x="596" y="394" className="diagram-label">
              {copy('工作区管理', 'Workspace manager')}
            </text>
          </g>
        </g>

        <g className="diagram-node diagram-runtime">
          <rect x="886" y="142" width="206" height="222" rx="18" />
          <text x="910" y="180" className="diagram-title">
            {copy('隔离环境', 'Isolated runtime')}
          </text>
          <g className="diagram-runtime-box">
            <rect x="910" y="205" width="158" height="44" rx="9" />
            <text x="930" y="233" className="diagram-label">
              {copy('主工作区', 'Main workspace')}
            </text>
          </g>
          <g className="diagram-runtime-box">
            <rect x="910" y="264" width="158" height="44" rx="9" />
            <text x="930" y="292" className="diagram-label">
              {copy('子任务工作区', 'Child workspace')}
            </text>
          </g>
          <text x="910" y="338" className="diagram-small">
            Docker · {copy('独立文件系统', 'isolated filesystems')}
          </text>
        </g>

        <g className="diagram-node diagram-output">
          <rect x="302" y="490" width="514" height="54" rx="16" />
          <text x="330" y="523" className="diagram-label">
            {copy('冻结验证与评分', 'Frozen verification & scoring')}
          </text>
          <text x="596" y="523" className="diagram-score">
            DRS
          </text>
          <text x="682" y="523" className="diagram-score">
            BTS Δ
          </text>
        </g>

        <path
          d="M238 254 H286"
          className="diagram-flow"
          markerEnd="url(#overview-arrow)"
        />
        <path
          d="M559 138 V194"
          className="diagram-flow"
          markerEnd="url(#overview-arrow)"
        />
        <path
          d="M816 254 H870"
          className="diagram-flow"
          markerEnd="url(#overview-arrow)"
        />
        <path
          d="M870 324 H816"
          className="diagram-flow diagram-flow-return"
          markerEnd="url(#overview-arrow)"
        />
        <path
          d="M559 446 V478"
          className="diagram-flow"
          markerEnd="url(#overview-arrow)"
        />
        <text x="248" y="240" className="diagram-edge-label">
          {copy('任务', 'tasks')}
        </text>
        <text x="576" y="170" className="diagram-edge-label">
          {copy('动作 / 观测', 'actions / observations')}
        </text>
        <text x="822" y="240" className="diagram-edge-label">
          {copy('执行', 'execute')}
        </text>
        <text x="824" y="352" className="diagram-edge-label">
          {copy('结果', 'results')}
        </text>
      </svg>
    </div>
  );
}
