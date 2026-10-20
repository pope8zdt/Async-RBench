import test from 'node:test';
import assert from 'node:assert/strict';
import {tabIndex, communityMarkup, copyCitation, legacyResearchDestination, sectionAt} from '../published/research.mjs';
import {matchingTasks, pageSlice, selectedRecord, resetTaskFilters} from '../published/task-browser.mjs';

test('tabs support arrows, Home and End without moving on unrelated keys',()=>{
  assert.equal(tabIndex('ArrowRight',1,2),0);assert.equal(tabIndex('ArrowLeft',0,2),1);
  assert.equal(tabIndex('Home',1,2),0);assert.equal(tabIndex('End',0,2),1);assert.equal(tabIndex('Tab',1,2),null);
});
test('navigation tracks the section at the header, independent of viewport aspect ratio',()=>{
  assert.equal(sectionAt([{id:'tasks',top:-1065},{id:'leaderboard',top:100.175},{id:'participate',top:3174}],144),'leaderboard');
  assert.equal(sectionAt([{id:'framework',top:600}],144),null);
});
test('empty community snapshot is distinct from invalid or unapproved data',()=>{
  assert.match(communityMarkup({schema:'async-rbench-community-board-1',entries:[]},'en'),/class="repository-empty"/);
  assert.throws(()=>communityMarkup({schema:'other',entries:[]}));
  assert.throws(()=>communityMarkup({schema:'async-rbench-community-board-2',entries:[{metrics:{drs:99},evidence:'private'}]}));
});
test('citation copying returns an explicit manual fallback on permission failure',async()=>{
  let copied;assert.equal(await copyCitation('bib',async s=>{copied=s;}),true);assert.equal(copied,'bib');
  assert.equal(await copyCitation('bib',async()=>{throw Error('denied');}),false);
});
test('task filters compose; pagination clamps after changing filters',()=>{
  const items=[{id:'a',title:'Repair code',source:'swe-bench',difficulty:'hard'},{id:'b',title:'Find source',source:'gaia2',difficulty:'medium'}];
  assert.deepEqual(matchingTasks(items,{query:'REPAIR',source:'swe-bench',difficulty:'hard'}),[items[0]]);
  assert.deepEqual(matchingTasks(items,{query:'none'}),[]);
  assert.deepEqual(pageSlice([],9,12),{items:[],page:1,pages:1,total:0});
  assert.equal(pageSlice(items,9,12).page,1);
});
test('reset clears filter values before rendering, not before the browser default reset',()=>{
  const fields=[{value:'secure-release'},{value:'swe-bench'},{value:'hard'}];
  let prevented=false,rendered;
  resetTaskFilters({preventDefault:()=>{prevented=true;}},fields,()=>{rendered=fields.map(f=>f.value);});
  assert.equal(prevented,true);assert.deepEqual(rendered,['','','']);
});
test('archived record links select the correct case and event',()=>{
  const cases=[{id:'release',events:[{seq:165},{seq:195}]},{id:'defer',events:[{seq:150}]}];
  assert.equal(selectedRecord(cases,'defer',150).event.seq,150);
  assert.equal(selectedRecord(cases,'release',195).event.seq,195);
  assert.equal(selectedRecord(cases,'unknown',999).case.id,'release');
});
test('legacy trajectory bookmarks reach the browser with their record intact',()=>{
  assert.equal(legacyResearchDestination('https://example.org/Async-RBench/benchmark/?case=defer&seq=150#trajectories'),'/Async-RBench/tasks/?case=defer&seq=150#records');
  assert.equal(legacyResearchDestination('https://example.org/Async-RBench/benchmark/index.html?case=defer&seq=150#trajectories'),'/Async-RBench/tasks/?case=defer&seq=150#records');
  assert.equal(legacyResearchDestination('https://example.org/Async-RBench/benchmark/#guide'),'https://github.com/pope8zdt/Async-RBench#quick-start');
  assert.equal(legacyResearchDestination('https://example.org/benchmark/#framework'),null);
});

const summary=()=>({id:'a'.repeat(32),metadata:{agent:'Research agent',model:'Test model',organization:'Research group',code_revision:'b'.repeat(40)},metrics:{drs:45.1,success:38.2,tasks:200,episodes:600,repetitions:3},submitter:'contributor',reviewer:'maintainer',reviewed_at:'2026-10-19T00:00:00Z',verification:'maintainer-reviewed',score_policy_version:'async-rbench-runtime-boundaries-1'});
test('approved summaries render without private fields; both published schemas work',()=>{
  const v2=summary();
  assert.match(communityMarkup({schema:'async-rbench-community-board-2',entries:[v2]}),/Research agent/);
  const {id,...fields}=v2;
  const v1={...fields,issue:42,url:'https://github.com/pope8zdt/Async-RBench/issues/42',review_url:'https://github.com/pope8zdt/Async-RBench/issues/42#issuecomment-123',receipt_sha256:'c'.repeat(64)};
  const html=communityMarkup({schema:'async-rbench-community-board-1',entries:[v1]});
  assert.match(html,/45\.1/);assert.doesNotMatch(html,/issuecomment|receipt_sha256|\/issues\//);
  assert.throws(()=>communityMarkup({schema:'async-rbench-community-board-1',entries:[{...v1,url:'https://example.org/private'}]}));
  assert.throws(()=>communityMarkup({schema:'async-rbench-community-board-2',entries:[{...v2,evidence:'private'}]}));
  assert.throws(()=>communityMarkup({schema:'async-rbench-community-board-2',entries:[{...v2,reviewer:'contributor'}]}));
  assert.throws(()=>communityMarkup({schema:'async-rbench-community-board-2',entries:[{...v2,id:1e31}]}));
});
