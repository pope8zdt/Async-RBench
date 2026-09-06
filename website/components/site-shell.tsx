'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { Menu } from 'lucide-react';
import { useState } from 'react';
import { repositoryUrl } from '@/lib/repository';
const links = [
  ['/', '概览'],
  ['/tasks', '任务库'],
  ['/leaderboard', 'Leaderboard'],
  ['/evaluate', '开始评测'],
  ['/docs', '教程与协议'],
];
export function SiteShell({ children }: { children: React.ReactNode }) {
  const path = usePathname();
  const [open, setOpen] = useState(false);
  return (
    <>
      <header className="site-header">
        <div className="header-inner">
          <Link href="/" className="brand">
            Async-RBench
          </Link>
          <button
            className="mobile-menu"
            onClick={() => setOpen(!open)}
            aria-label="切换导航"
            aria-expanded={open}
            aria-controls="main-navigation"
          >
            <Menu />
          </button>
          <nav
            id="main-navigation"
            className={open ? 'nav open' : 'nav'}
            aria-label="主导航"
          >
            {links.map(([href, label]) => (
              <Link
                key={href}
                href={href}
                className={
                  (href === '/' ? path === href : path.startsWith(href))
                    ? 'active'
                    : ''
                }
                onClick={() => setOpen(false)}
              >
                {label}
              </Link>
            ))}
          </nav>
          <span className="version">v11.0.0</span>
        </div>
      </header>
      <main>{children}</main>
      <footer className="site-footer">
        <Link href="/" className="footer-brand">
          Async-RBench
        </Link>
        <span>201个高质量任务 · Linear / Async 配对评测</span>
        <Link href="/docs#protocol">评测协议</Link>
        <a className="text-link" href={repositoryUrl}>
          GitHub
        </a>
      </footer>
    </>
  );
}
