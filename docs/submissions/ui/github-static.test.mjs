import test from 'node:test';
import assert from 'node:assert/strict';
import {preparePublicSubmission} from './github-static.mjs';
import {SubmissionController} from './github-app.mjs';

const packet = () => ({schema:'async-rbench-public-submission-1',metadata:{agent:'Example agent',model:'Example model',organization:'Example team',code_revision:'a'.repeat(40)},coverage:{tasks:200,repetitions:3,episodes:600},sha256:'b'.repeat(64)});
const file = value => ({name:'submission.json',size:1000,text:async()=>JSON.stringify(value)});

test('public draft uses the exact reviewed receipt fingerprint and fixed GitHub host', () => {
  const draft = preparePublicSubmission(packet());
  const url = new URL(draft.url);
  assert.equal(url.origin,'https://github.com');
  assert.equal(url.pathname,'/pope8zdt/Async-RBench/issues/new');
  assert.equal(url.searchParams.get('title'),'[Result submission] Example agent');
  assert.match(url.searchParams.get('body'),/Coverage: 200 tasks, 3 repetitions/);
  assert.ok(draft.body.includes(`<!-- async-rbench-receipt:${'b'.repeat(64)} -->`));
});

test('static preparation never sends the selected file over the network', async () => {
  const controller = new SubmissionController(()=>{throw Error('unexpected network');},()=>{},{staticMode:true,communityUrl:'/Async-RBench/data/community.json'});
  await controller.upload(file(packet()));
  assert.equal(controller.state.error,null);
  assert.equal(controller.state.draft.metadata.agent,'Example agent');
  await controller.upload(file({schema:'async-rbench-community-receipt-1',manifest:'private',scores:[]}));
  assert.equal(controller.state.error,'invalid');
  assert.equal(controller.state.draft,null);
});

test('static community loading respects the deployed project prefix', async () => {
  const controller = new SubmissionController(async(url,options)=>{
    assert.equal(url,'/Async-RBench/data/community.json');
    assert.equal(options,undefined);
    return {ok:true,json:async()=>({schema:'async-rbench-community-board-1',entries:[]})};
  },()=>{},{staticMode:true,communityUrl:'/Async-RBench/data/community.json'});
  await controller.setView('community');
  assert.deepEqual(controller.state.entries,[]);
  assert.equal(controller.state.error,null);
});

for (const kind of ['html','extra','wrong_hash','private','coverage','url']) {
  test(`public picker rejects ${kind} instead of copying it into a draft`,()=>{
    const value=packet();
    if(kind==='html') value.metadata.agent='<script>alert(1)</script>';
    if(kind==='extra') value.metadata.secret='private';
    if(kind==='wrong_hash') value.sha256='b'.repeat(63);
    if(kind==='private') value.manifest='private';
    if(kind==='coverage') value.coverage.repetitions=true;
    if(kind==='url') value.url='https://evil.example';
    assert.throws(()=>preparePublicSubmission(value));
  });
}
