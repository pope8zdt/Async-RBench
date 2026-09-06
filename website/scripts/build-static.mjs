import { spawnSync } from 'node:child_process';
import { writeFileSync } from 'node:fs';

// Native Next export supports Pages subpaths and domain-root hosting.
const result = spawnSync(
  process.execPath,
  ['node_modules/next/dist/bin/next', 'build', '--webpack'],
  {
    stdio: 'inherit',
    env: {
      ...process.env,
      SITE_STATIC_EXPORT: '1',
      NEXT_TELEMETRY_DISABLED: '1',
    },
  },
);
if (result.error) throw result.error;
if (result.status !== 0) process.exit(result.status || 1);
// GitHub Pages must serve underscore-prefixed framework assets unchanged.
writeFileSync('out/.nojekyll', '');
