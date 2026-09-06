'use client';
import {
  createContext,
  useContext,
  useEffect,
  useSyncExternalStore,
} from 'react';
import { usePathname } from 'next/navigation';
import {
  decodePreferences,
  preferenceKey,
  savePreferences,
  type Preferences,
} from '@/lib/preferences.mjs';

type PreferenceContext = Preferences & {
  toggleLocale: () => void;
  toggleTheme: () => void;
};
const Context = createContext<PreferenceContext>({
  locale: 'zh',
  theme: 'light',
  toggleLocale: () => {},
  toggleTheme: () => {},
});

const initial: Preferences = { locale: 'zh', theme: 'light' };
let current: Preferences | undefined;
const listeners = new Set<() => void>();
function readSnapshot() {
  if (!current) {
    let stored = null;
    try {
      stored = localStorage.getItem(preferenceKey);
    } catch {
      /* Storage is optional. */
    }
    current = decodePreferences(
      stored,
      matchMedia('(prefers-color-scheme: dark)').matches,
    );
  }
  return current;
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  const sync = (event: StorageEvent) => {
    if (event.key === preferenceKey || event.key === null) {
      current = decodePreferences(
        event.newValue,
        matchMedia('(prefers-color-scheme: dark)').matches,
      );
      listener();
    }
  };
  window.addEventListener('storage', sync);
  return () => {
    listeners.delete(listener);
    window.removeEventListener('storage', sync);
  };
}
function update(next: Preferences) {
  current = next;
  try {
    savePreferences(localStorage, next);
  } catch {
    /* Storage is optional. */
  }
  listeners.forEach((listener) => listener());
}

export function PreferencesProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const preferences = useSyncExternalStore(
    subscribe,
    readSnapshot,
    () => initial,
  );
  const path = usePathname();
  const titles = [
    ['/tasks', '任务库', 'Tasks'],
    ['/leaderboard', '排行榜', 'Leaderboard'],
    ['/evaluate', '开始评测', 'Run the benchmark'],
    ['/docs', '教程', 'Docs'],
    ['/runs/', '实验详情', 'Run details'],
  ];
  const title = titles.find(([prefix]) => path.includes(prefix));
  const pageTitle = title
    ? `${title[preferences.locale === 'zh' ? 1 : 2]} | Async-RBench`
    : 'Async-RBench';
  useEffect(() => {
    document.documentElement.classList.toggle(
      'dark',
      preferences.theme === 'dark',
    );
    document.documentElement.lang =
      preferences.locale === 'zh' ? 'zh-CN' : 'en';
  }, [preferences]);
  return (
    <Context.Provider
      value={{
        ...preferences,
        toggleLocale: () =>
          update({
            ...preferences,
            locale: preferences.locale === 'zh' ? 'en' : 'zh',
          }),
        toggleTheme: () =>
          update({
            ...preferences,
            theme: preferences.theme === 'dark' ? 'light' : 'dark',
          }),
      }}
    >
      <title>{pageTitle}</title>
      {children}
    </Context.Provider>
  );
}
export function usePreferences() {
  return useContext(Context);
}
export function useCopy() {
  const { locale } = usePreferences();
  return (zh: string, en: string) => (locale === 'zh' ? zh : en);
}
export function T({ zh, en }: { zh: string; en: string }) {
  const t = useCopy();
  return t(zh, en);
}
