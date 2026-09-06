import type { Metadata } from 'next';
import { SiteShell } from '@/components/site-shell';
import { assetPath } from '@/lib/asset-path';
import './globals.css';
export const metadata: Metadata = {
  icons: { icon: assetPath('/favicon.svg') },
  title: {
    default: 'Async-RBench | 异步重规划评测',
    template: '%s | Async-RBench',
  },
  description: 'Async-RBench 的评测协议、47-case 主实验结果与本地运行教程。',
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
