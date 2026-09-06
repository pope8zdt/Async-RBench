export type Preferences = { locale: 'zh' | 'en'; theme: 'light' | 'dark' };
export const preferenceKey: string;
export function decodePreferences(
  value: string | null,
  systemDark?: boolean,
): Preferences;
export function savePreferences(
  storage: Pick<Storage, 'setItem'>,
  preferences: Preferences,
): boolean;
