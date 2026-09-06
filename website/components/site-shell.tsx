'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Menu, Moon, Sun, X } from 'lucide-react';
import { useState } from 'react';
import { repositoryUrl } from '@/lib/repository';
import { useCopy, usePreferences, T } from '@/components/preferences';

const links = [
  ['/', '首页', 'Home'],
  ['/tasks', '任务', 'Tasks'],
  ['/leaderboard', '榜单', 'Leaderboard'],
  ['/evaluate', '运行', 'Run'],
  ['/docs', '教程', 'Docs'],
];
export function SiteShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  const t = useCopy();
  const { locale, theme, toggleLocale, toggleTheme } = usePreferences();
  return (
    <>
      <header className="site-header">
        <div className="header-inner">
          <Link href="/" className="brand" onClick={() => setOpen(false)}>
            Async-RBench
          </Link>
          <nav
            id="main-navigation"
            className={open ? 'nav open' : 'nav'}
            aria-label={t('主导航', 'Main navigation')}
          >
            {links.map(([href, zh, en]) => (
              <Link
                key={href}
                href={href}
                className={
                  (href === '/' ? path === href : path.startsWith(href))
                    ? 'active'
                    : ''
                }
                aria-current={
                  (href === '/' ? path === href : path.startsWith(href))
                    ? 'page'
                    : undefined
                }
                onClick={() => setOpen(false)}
              >
                {t(zh, en)}
              </Link>
            ))}
          </nav>
          <div className="header-actions">
            <button
              type="button"
              className="preference-button language-button"
              onClick={toggleLocale}
              aria-label={locale === 'zh' ? 'Switch to English' : '切换为中文'}
            >
              {locale === 'zh' ? 'EN' : '中文'}
            </button>
            <button
              type="button"
              className="preference-button"
              onClick={toggleTheme}
              aria-label={
                theme === 'dark'
                  ? t('切换至浅色主题', 'Switch to light theme')
                  : t('切换至深色主题', 'Switch to dark theme')
              }
            >
              {theme === 'dark' ? <Sun size={18} /> : <Moon size={18} />}
            </button>
          </div>
          <button
            type="button"
            className="mobile-menu"
            onClick={() => setOpen(!open)}
            aria-label={t('切换导航', 'Toggle navigation')}
            aria-expanded={open}
            aria-controls="main-navigation"
          >
            {open ? <X size={21} /> : <Menu size={21} />}
          </button>
        </div>
      </header>
      <main>{children}</main>
      <footer className="site-footer">
        <Link href="/" className="footer-brand">
          Async-RBench
        </Link>
        <span>
          <T zh="201个高质量任务" en="201 high-quality tasks" />
        </span>
        <a href={repositoryUrl}>GitHub ↗</a>
      </footer>
    </>
  );
}
