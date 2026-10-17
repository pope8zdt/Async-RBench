import test from 'node:test';
import assert from 'node:assert/strict';
import { SubmissionController } from './github-app.mjs';

const deferred = () => { let resolve; const promise = new Promise(r => resolve = r); return {promise,resolve}; };
const file = (name, text = '{}') => ({name,size:text.length,text:async()=>text});
const response = value => ({ok:true,json:async()=>value});

test('changing view invalidates an in-flight receipt read', async () => {
  const read = deferred();
  const controller = new SubmissionController(async url => {
    assert.equal(url,'/api/community');
    return response({entries:[]});
  });
  const upload = controller.upload({name:'slow.json',size:20,text:()=>read.promise});
  await controller.setView('community');
  read.resolve('{}');
  await upload;
  assert.equal(controller.state.view,'community');
  assert.equal(controller.state.draft,null);
  assert.equal(controller.state.busy,false);
});

test('newer receipt wins over a delayed response', async () => {
  const first = deferred();
  let count = 0;
  const controller = new SubmissionController(async () => ++count === 1 ? first.promise : response({metadata:{agent:'new'}}));
  const old = controller.upload(file('old.json'));
  await new Promise(r=>setImmediate(r));
  await controller.upload(file('new.json'));
  first.resolve(response({metadata:{agent:'old'}}));
  await old;
  assert.equal(controller.state.draft.metadata.agent,'new');
  assert.equal(controller.state.fileName,'new.json');
});

test('invalid input clears a previously prepared GitHub draft', async () => {
  const controller = new SubmissionController(async()=>response({url:'https://github.com/example'}));
  await controller.upload(file('valid.json'));
  await controller.upload(file('invalid.json','{'));
  assert.equal(controller.state.draft,null);
  assert.equal(controller.state.error,'invalid');
});

test('large uploads never reach the transport', async () => {
  const controller = new SubmissionController(()=>{throw new Error('must not fetch');});
  await controller.upload({name:'huge.json',size:9*1024*1024,text:()=>{throw new Error('must not read');}});
  assert.equal(controller.state.error,'large');
});

test('preparing and browsing use only local endpoints, never GitHub writes', async () => {
  const controller = new SubmissionController(async (url, options) => {
    if (url === '/api/prepare') {
      assert.equal(options.method,'POST');
      assert.deepEqual(JSON.parse(options.body),{receipt:{schema:'example'}});
      return response({body:'public summary'});
    }
    assert.equal(url,'/api/community');
    assert.equal(options,undefined);
    return response({entries:[{issue:7}]});
  });
  await controller.upload(file('receipt.json','{"schema":"example"}'));
  assert.equal(controller.state.draft.body,'public summary');
  await controller.setView('community');
  assert.equal(controller.state.entries[0].issue,7);
});
