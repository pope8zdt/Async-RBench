export const themes = [
  [
    'delayed_authoritative_result',
    '权威结果延迟到达',
    '下游工作开始后，关键结果才完成。',
  ],
  [
    'late_or_out_of_order_superseded_result',
    '过时结果与乱序交付',
    '较新的结果已经到达，旧结果随后出现。',
  ],
  [
    'partial_then_complete_result',
    '部分结果到完整结果',
    '根据逐步补全的信息修正判断。',
  ],
  [
    'conflicting_valid_results',
    '有效结果相互冲突',
    '协调多个独立工作流的分歧。',
  ],
  [
    'duplicate_or_replayed_completion',
    '重复与重放结果',
    '识别同一完成结果的再次交付。',
  ],
  [
    'child_failure_or_implicit_error',
    '子任务失败',
    '处理显式失败与结果中的隐式错误。',
  ],
  [
    'task_scope_or_dependency_change',
    '任务范围与依赖变化',
    '调整已经开始执行的计划。',
  ],
  [
    'straggler_under_resource_pressure',
    '资源压力下的慢任务',
    '在资源约束下重新分配工作。',
  ],
] as const;
export const metrics = [
  {
    name: 'Linear BTS',
    full: '线性执行 · 基础任务分',
    key: 'linear_base_task_score',
    description: '在线性执行条件下，基础任务完成的正确性。',
  },
  {
    name: 'Async BTS',
    full: '异步执行 · 基础任务分',
    key: 'async_base_task_score',
    description: '在异步事件条件下，基础任务完成的正确性。',
  },
  {
    name: 'Async DRS',
    full: '异步执行 · 动态重规划分',
    key: 'async_dynamic_replanning_score',
    description: '结合过程观测与异步结果，衡量每个事件的重规划质量。',
  },
];
export type Experiment = {
  id: string;
  sourceSha256: string;
  date: string | null;
  model: string;
  version: string;
  caseCount: number;
  completedCases: number;
  episodes: number;
  scored: number;
  linear: number | null;
  async: number | null;
  drs: number | null;
  observedLinear: number | null;
  observedAsync: number | null;
  observedDrs: number | null;
  pairedComplete: boolean;
  themeCount: number;
  themeScores: Record<string, number | null>;
  published: boolean;
  scope: string;
};
export function score(value: number | null) {
  return value === null ? '—' : (value * 100).toFixed(1);
}
