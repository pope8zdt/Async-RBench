import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {loadArchive} from '../published/assets/evidence-loader.mjs';
import {defaultEvents,keyEvents,readEvidenceLocation} from '../published/assets/evidence-state.mjs';
import {focusEvidence,recordPreview} from '../published/assets/evidence-view.mjs';
import {participantAction,participantState,stepFromHash} from '../published/participation.mjs';
import {legacyDestination} from '../published/entry-route.mjs';
import {isFigureLink} from '../published/figure-viewer.mjs';

const archive = JSON.parse(await readFile(new URL('../published/data/trajectories.public.json', import.meta.url)));

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
