export const preferenceKey = 'async-rbench.preferences';
export function decodePreferences(value, systemDark = false) {
  let saved;
  try {
    saved = JSON.parse(value);
  } catch {
    saved = null;
  }
  return {
    locale: saved?.locale === 'en' ? 'en' : 'zh',
    theme: ['light', 'dark'].includes(saved?.theme)
      ? saved.theme
      : systemDark
        ? 'dark'
        : 'light',
  };
}
export function savePreferences(storage, preferences) {
  try {
    storage.setItem(preferenceKey, JSON.stringify(preferences));
    return true;
  } catch {
    return false;
  }
}
