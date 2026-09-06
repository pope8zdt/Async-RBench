import type { Experiment } from './content';
export type MetricKey = 'linear' | 'async' | 'drs' | 'delta';
export function coverageStatus(record: Experiment): 'complete' | 'incomplete';
export function executionStatus(record: Experiment): string;
export function reviewStatus(
  record: Experiment,
): 'self_reported' | 'materials_reviewed' | 'independently_reproduced';
export function metricValue(
  record: Experiment,
  metric: MetricKey,
): number | null;
export function leaderboardRows(
  records: Experiment[],
  metric: MetricKey,
  query?: string,
): {
  record: Experiment;
  value: number | null;
  complete: boolean;
  rank: number | null;
  group: number;
}[];
