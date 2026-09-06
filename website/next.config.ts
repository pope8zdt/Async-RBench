import type { NextConfig } from 'next';

const basePath = (process.env.NEXT_PUBLIC_BASE_PATH || '').replace(/\/$/, '');
if (basePath && !/^\/[A-Za-z0-9._/-]+$/.test(basePath)) {
  throw new Error(
    'NEXT_PUBLIC_BASE_PATH must be a URL path such as /async-rbench',
  );
}
const nextConfig: NextConfig = {
  basePath,
  trailingSlash: true,
  ...(process.env.SITE_STATIC_EXPORT === '1'
    ? { output: 'export' as const }
    : {}),
};

export default nextConfig;
