// Pure derived display state; implemented against archived-record regression tests.
export function formatTime(ms) {
  const tenths = Math.max(0, Math.round(ms / 100));
  const minutes = Math.floor(tenths / 600);
  const seconds = (tenths % 600) / 10;
  return `${String(minutes).padStart(2, '0')}:${seconds.toFixed(1).padStart(4, '0')}`;
}

export function buildClock(trajectory) {
  let at = 0;
  const points = trajectory.events.map((event,index,events) => {
    if (index) at += Math.max(100, Math.min(1800, (event.elapsed_ms-events[index-1].elapsed_ms)/10));
    return {seq:event.seq, at, elapsed:event.elapsed_ms};
  });
  return {points, duration:at+1000};
}

export function frameAt(trajectory,clock,time) {
  const points=clock.points;
  let index=0;
  while(index+1<points.length && points[index+1].at<=time) index++;
  const current=points[index], next=points[index+1];
  const fraction=next ? Math.max(0,Math.min(1,(time-current.at)/(next.at-current.at))) : 0;
  return {index,event:trajectory.events[index],elapsed:current.elapsed+(next?Math.max(0,next.elapsed-current.elapsed)*fraction:0)};
}

export function observedState(trajectory,seq) {
  const children=trajectory.lanes.filter(l=>l.id.startsWith('child')).map(l=>({...l,state:'pending'}));
  const completions=new Map(), artifacts=new Map(), evidence={};
  let action=null, actionResult=null, endpoint=null, lastPresentation=null;
  for(const event of trajectory.events) {
    if(event.seq>seq) break;
    const r=event.record, child=children.find(c=>c.id===event.lane);
    if(child) {
      if(event.type==='child_started') child.state='running';
      if(event.type==='child_completed') child.state='completed';
      if(event.type==='child_cancelled') child.state='cancelled';
      if(event.type==='child_failed') child.state='failed';
    }
    if(r.completion_id && ['result_delivered','result_presented','result_delivery_evaluator_fact'].includes(event.type)) {
      if(!completions.has(r.completion_id)) completions.set(r.completion_id,{id:r.completion_id,child:null,deliveries:0,presentations:0,replays:0,decision:null});
      const row=completions.get(r.completion_id);
      if(r.child_id) row.child=r.child_id;
      if(event.type==='result_delivered') row.deliveries++;
      if(event.type==='result_presented') { row.presentations++; lastPresentation=event; }
      if(r.replayed===true) row.replays++;
    }
    if(event.type==='main_action') {
      action=event; actionResult=null;
      if(r.kind==='acknowledge_result' && completions.has(r.completion_id)) completions.get(r.completion_id).decision=r.decision;
    }
    if(event.type==='main_action_finished' && action?.record.action_id===r.action_id) actionResult=event;
    if(event.type==='child_path_promotion_result' && r.success===true) artifacts.set(r.destination_path,event);
    if(r.evidence) Object.assign(evidence,r.evidence);
    if(event.type==='episode_ended') endpoint=event;
  }
  return {children,completions:[...completions.values()],artifacts:[...artifacts.values()],evidence,action,actionResult,endpoint,lastPresentation};
}
