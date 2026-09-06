import type { Metadata } from 'next';
import { SiteShell } from '@/components/site-shell';
import { assetPath } from '@/lib/asset-path';
import './globals.css';
export const metadata: Metadata = {
  icons: { icon: assetPath('/favicon.svg') },
  title: {
    default: 'Async-RBench — 异步 Agent 评测',
    template: '%s | Async-RBench',
  },
  description:
    '评测主 Agent 在异步事件下的结果整合与动态重规划能力。Track A、实验记录与接入教程。',
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN">
      <body>
        <SiteShell>{children}</SiteShell>
      </body>
    </html>
  );
}
