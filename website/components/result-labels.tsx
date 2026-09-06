import { T } from '@/components/preferences';
import { themes } from '@/lib/content';

const reviewText = {
  self_reported: ['自行报告', 'Self-reported'],
  materials_reviewed: ['材料已审核', 'Materials reviewed'],
  independently_reproduced: ['已独立复现', 'Independently reproduced'],
} as const;

export function ReviewLabel({ status }: { status: keyof typeof reviewText }) {
  const [zh, en] = reviewText[status];
  return <T zh={zh} en={en} />;
}

const executionText: Record<string, readonly [string, string]> = {
  unknown: ['未知', 'Unknown'],
  running: ['运行中（已报告）', 'Running (reported)'],
  completed: ['已结束（已报告）', 'Completed (reported)'],
  failed: ['失败（已报告）', 'Failed (reported)'],
  stopped: ['已停止（已报告）', 'Stopped (reported)'],
};

export function ExecutionLabel({ status }: { status: string }) {
  const [zh, en] = executionText[status] ?? executionText.unknown;
  return <T zh={zh} en={en} />;
}

const themeText: Record<(typeof themes)[number][0], string> = {
  delayed_authoritative_result: 'Delayed authoritative results',
  late_or_out_of_order_superseded_result: 'Stale and out-of-order results',
  partial_then_complete_result: 'Partial to complete results',
  conflicting_valid_results: 'Conflicting valid results',
  duplicate_or_replayed_completion: 'Duplicate and replayed results',
  child_failure_or_implicit_error: 'Subtask failures',
  task_scope_or_dependency_change: 'Scope and dependency changes',
  straggler_under_resource_pressure: 'Stragglers under resource pressure',
};

export function ThemeLabel({ theme }: { theme: (typeof themes)[number] }) {
  return <T zh={theme[1]} en={themeText[theme[0]]} />;
}
