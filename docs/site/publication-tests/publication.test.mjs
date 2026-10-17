import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {readdir} from 'node:fs/promises';
import {runInNewContext} from 'node:vm';
import {loadArchive} from '../published/assets/evidence-loader.mjs';
import {defaultEvents,keyEvents,readEvidenceLocation} from '../published/assets/evidence-state.mjs';
import {focusEvidence,recordPreview} from '../published/assets/evidence-view.mjs';
import {participantAction,participantState,stepFromHash} from '../published/participation.mjs';
import {legacyDestination} from '../published/entry-route.mjs';
import {isFigureLink} from '../published/figure-viewer.mjs';

const archive = JSON.parse(await readFile(new URL('../published/data/trajectories.public.json', import.meta.url)));

async function htmlPages(directory) {
  const pages = [];
  for (const item of await readdir(directory, {withFileTypes:true})) {
    const path = new URL(item.name + (item.isDirectory() ? '/' : ''), directory);
    if (item.isDirectory()) pages.push(...await htmlPages(path));
    else if (item.name.endsWith('.html')) pages.push(path);
  }
  return pages;
}

test('every page starts in English even with an old Chinese preference or blocked storage', async () => {
  for (const path of await htmlPages(new URL('../published/', import.meta.url))) {
    const html = await readFile(path, 'utf8');
    const head = html.split('</head>')[0];
    const scripts = [...head.matchAll(/<script([^>]*)>([\s\S]*?)<\/script>/g)]
      .filter(([,attrs]) => !/\bsrc=/.test(attrs) && !attrs.includes('application/json'));
    for (const blocked of [false, true]) {
      const root = {lang:html.match(/<html[^>]*lang="([^"]+)"/)[1],dataset:{}};
      const context = {document:{documentElement:root}, matchMedia:()=>({matches:false}),
        localStorage:{getItem:()=>{if (blocked) throw new Error('storage unavailable'); return '{"language":"zh","theme":"dark"}';}}};
      for (const [,,script] of scripts) runInNewContext(script,context);
      assert.equal(root.lang,'en',`${path.pathname}; blocked storage=${blocked}`);
      if (!blocked && !['/index.html','/entry/index.html'].some(suffix=>path.pathname.endsWith('/published'+suffix))) {
        assert.equal(root.dataset.theme,'dark',`${path.pathname}: preserve the saved theme`);
      }
    }
  }
});

test('cover routing does not overwrite the English initializer with a saved language', async t => {
  const root = {lang:'en'};
  for (const [name,value] of Object.entries({document:{documentElement:root},
    localStorage:{getItem:()=>'{"language":"zh"}'},
    location:{href:'https://example.org/',replace:()=>assert.fail('unexpected redirect')},
  })) {
    const prior=Object.getOwnPropertyDescriptor(globalThis,name);
    Object.defineProperty(globalThis,name,{value,configurable:true});
    t.after(()=>prior?Object.defineProperty(globalThis,name,prior):delete globalThis[name]);
  }
  await import('../published/entry-route.mjs?language-default-test');
  assert.equal(root.lang,'en');
});

test('figure zoom works under the deployed project path', () => {
  assert.equal(isFigureLink('/assets/getting-started-en.svg?v=1'),true);
  assert.equal(isFigureLink('/Async-RBench/assets/getting-started-en.svg?v=1'),true);
  assert.equal(isFigureLink('https://other.example/assets/getting-started-en.svg'),false);
  assert.equal(isFigureLink('/Async-RBench/data/corpus.json'),false);
});

test('public host can read only the reviewed archive format', async () => {
  assert.equal(await loadArchive('/data/trajectories.public.json', 'pope8zdt.github.io', async () => ({ok:true,json:async()=>archive})), archive);
  await assert.rejects(loadArchive('/bad', 'pope8zdt.github.io', async () => ({ok:true,json:async()=>({local_only:true,cases:[]})})), /Invalid/);
  await assert.rejects(loadArchive('/bad', 'pope8zdt.github.io', async () => ({ok:false})), /unavailable/);
});

for (const c of archive.cases) {
  test(`all evidence and deep links resolve for ${c.id}`, () => {
    assert.equal(focusEvidence(c).length, 3);
    assert.ok(keyEvents(c).length >= 3);
    const state = readEvidenceLocation(`https://pope8zdt.github.io/Async-RBench/benchmark/?case=${c.id}#trajectories`, archive.cases);
    assert.equal(state.caseId,c.id);
    assert.equal(state.seq,defaultEvents[c.id]);
    for (const e of c.events) assert.equal(typeof recordPreview(e).text, 'string');
  });
}

test('guide navigation and shell selection do not execute an evaluation', () => {
  let state=participantState();
  for(let step=0;step<4;step++) {assert.equal(state.step,step);state=participantAction(state,{type:'next'});}
  assert.equal(state.step,3);
  state=participantAction(state,{type:'shell',value:'powershell'});
  assert.equal(state.shell,'powershell');
  assert.equal(stepFromHash('#running'),2);
  assert.equal(stepFromHash('#unknown'),null);
});

test('cover keeps legacy trajectory bookmarks', () => {
  assert.equal(legacyDestination('https://example.org/?case=continue#trajectories'),'/benchmark/?case=continue#trajectories');
  assert.equal(legacyDestination('https://example.org/'),null);
});
