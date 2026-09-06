import type { Metadata } from 'next';
import { SiteShell } from '@/components/site-shell';
import { assetPath } from '@/lib/asset-path';
import { PreferencesProvider } from '@/components/preferences';
import './globals.css';
export const metadata: Metadata = {
  icons: { icon: assetPath('/favicon.svg') },
  description:
    'Async-RBench：201个高质量任务，异步重规划评测、主实验结果与本地运行教程。',
};
export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="zh-CN" suppressHydrationWarning>
      <head>
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var p=JSON.parse(localStorage.getItem('async-rbench.preferences')||'null');var dark=p&&['light','dark'].includes(p.theme)?p.theme==='dark':matchMedia('(prefers-color-scheme: dark)').matches;document.documentElement.classList.toggle('dark',dark);}catch(e){document.documentElement.classList.toggle('dark',matchMedia('(prefers-color-scheme: dark)').matches);}})();`,
          }}
        />
      </head>
      <body>
        <PreferencesProvider>
          <SiteShell>{children}</SiteShell>
        </PreferencesProvider>
      </body>
    </html>
  );
}
