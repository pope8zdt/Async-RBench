'use client';
import Link from 'next/link';
import { usePathname } from 'next/navigation';
import { ArrowUpRight, GitBranch, Menu } from 'lucide-react';
import { useState } from 'react';
import { repositoryUrl } from '@/lib/repository';
const links = [
  ['/', '概览'],
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
            <span className="brand-symbol">
              <GitBranch size={22} />
            </span>
            <span>
              Async<span className="brand-light">-RBench</span>
            </span>
            <small>LAB</small>
          </Link>
          <button
            className="mobile-menu"
            onClick={() => setOpen(!open)}
            aria-label="切换导航"
          >
            <Menu />
          </button>
          <nav className={open ? 'nav open' : 'nav'} aria-label="主导航">
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
          <span className="version">
            <span />
            v11.0.0
          </span>
        </div>
      </header>
      <main>{children}</main>
      <footer className="site-footer">
        <Link href="/" className="footer-brand">
          Async-RBench
        </Link>
        <span>异步结果整合与动态重规划评测</span>
        <Link href="/docs#protocol">
          评测协议 <ArrowUpRight size={14} />
        </Link>
        <a className="text-link" href={repositoryUrl}>
          GitHub <ArrowUpRight size={14} />
        </a>
      </footer>
    </>
  );
}
