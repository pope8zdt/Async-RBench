import test from 'node:test';
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { join } from 'node:path';

const root = 'out';
const base = (process.env.NEXT_PUBLIC_BASE_PATH || '').replace(/\/$/, '');
const data = JSON.parse(readFileSync('public/data/experiments.json', 'utf8'));

test('all public routes exist as static HTML, including every experiment', () => {
  for (const route of [
    '',
    'evaluate',
    'docs',
    'leaderboard',
    ...data.records.map((r) => `runs/${r.id}`),
  ]) {
    assert.ok(
      existsSync(join(root, route, 'index.html')),
      `missing static route: /${route}`,
    );
  }
  assert.ok(existsSync(join(root, '404.html')));
});

test('HTML assets and internal links resolve under the configured hosting path', () => {
  for (const route of [
    '',
    'evaluate',
    'docs',
    'leaderboard',
    `runs/${data.records[0].id}`,
  ]) {
    const html = readFileSync(join(root, route, 'index.html'), 'utf8');
    for (const [, href] of html.matchAll(/(?:src|href)="(\/[^"<>]*)"/g)) {
      const pathname = new URL(
        href.replaceAll('&amp;', '&'),
        'https://example.org',
      ).pathname;
      assert.ok(
        pathname === base || pathname.startsWith(`${base}/`),
        `outside base path: ${href}`,
      );
      const local = decodeURIComponent(pathname.slice(base.length)).replace(
        /^\//,
        '',
      );
      assert.ok(
        existsSync(join(root, local)) ||
          existsSync(join(root, local, 'index.html')),
        `missing target: ${href}`,
      );
    }
  }
  assert.deepEqual(
    JSON.parse(readFileSync(join(root, 'data/experiments.json'), 'utf8')),
    data,
  );
});
