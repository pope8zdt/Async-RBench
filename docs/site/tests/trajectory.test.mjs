import test from 'node:test';
import assert from 'node:assert/strict';
import { displayedEvents, stepIndex, eventPosition, laneState, completionState, recordExcerpt } from '../trajectory-logic.mjs';

const events = [
  {seq:1, elapsed_ms:0, lane:'child-1', type:'child_started', record:{}},
  {seq:5, elapsed_ms:100, lane:'delivery', type:'result_presented', record:{completion_id:'c1',delivery_occurrence_id:'o1'}},
  {seq:8, elapsed_ms:100, lane:'main', type:'main_action', record:{kind:'acknowledge_result',completion_id:'c1',decision:'use'}},
  {seq:12, elapsed_ms:300, lane:'delivery', type:'result_presented', record:{completion_id:'c1',delivery_occurrence_id:'o2'}},
  {seq:15, elapsed_ms:400, lane:'child-1', type:'child_cancelled', record:{}},
];
test('record excerpts retain exact command strings and identify partial commands', () => {
  assert.deepEqual(recordExcerpt({record:{command:'git diff main dev\n',exit_code:0}}), {kind:'command',text:'git diff main dev\n'});
  assert.deepEqual(recordExcerpt({record:{command_excerpt:'python validation_test.py'}}), {kind:'excerpt',text:'python validation_test.py'});
});
test('evidence is rendered without inventing terminal output or dropping false and zero values', () => {
  assert.deepEqual(recordExcerpt({record:{evidence:{passed:false,count:0}}}), {kind:'evidence',text:'passed: false\n\ncount: 0'});
  assert.deepEqual(recordExcerpt({record:{exit_code:0,success:true}}), {kind:'fields',text:'exit_code: 0\n\nsuccess: true'});
  assert.deepEqual(recordExcerpt({record:{}}), {kind:'fields',text:'{}'});
});
test('key moments retain source order and full displayed mode keeps every exported event', () => {
  const c={events,milestones:[{seq:12},{seq:5}]};
  assert.deepEqual(displayedEvents(c,'key').map(e=>e.seq),[5,12]);
  assert.equal(displayedEvents(c,'all').length,5);
  assert.equal(events[0].seq,1);
});
test('stepping clamps at both ends, seeking uses elapsed time, not equal event spacing', () => {
  assert.equal(stepIndex(0,-1,5),0);
  assert.equal(stepIndex(4,1,5),4);
  assert.equal(eventPosition(events[1],400),25);
  assert.equal(eventPosition(events[0],0),0);
});
test('lane states show observed lifecycle and rewind without retaining future cancellation', () => {
  assert.equal(laneState(events,'child-1',12),'running');
  assert.equal(laneState(events,'child-1',15),'cancelled');
  assert.equal(laneState(events,'child-1',0),'pending');
});
test('repeated presentation is not a new completion or a fabricated duplicate side effect', () => {
  const state=completionState(events,12);
  assert.deepEqual(state,[{id:'c1',presentations:2,decision:'use'}]);
  assert.deepEqual(completionState(events,5),[{id:'c1',presentations:1,decision:null}]);
});
