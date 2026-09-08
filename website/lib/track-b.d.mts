export const TRACK_B_FRAMEWORKS: ReadonlyArray<{
  id: string;
  label: string;
}>;

export function buildTrackBConfig(options: {
  framework: string;
  model: string;
  credentialEnv: string;
  component?: string;
}): string;

export function buildTrackBCommands(
  configName?: string,
  model?: string,
  framework?: string,
): string;
