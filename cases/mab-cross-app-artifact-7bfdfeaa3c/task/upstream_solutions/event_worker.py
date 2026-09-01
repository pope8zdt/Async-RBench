from __future__ import annotations
import argparse, hashlib, json, pathlib, time
CASE_ID='mab-cross-app-artifact-7bfdfeaa3c'; SOURCE_ID='coding:066'; EVENT='midi_timing_contract_completed'; EVENT_THEME='partial_then_complete_result'; MEANING='The completed MIDI contract revises playback and serialization without erasing lyrics, chat, collaborators, or version history.'; AUTHORITY={'contract': 'midi_timing_v2', 'ticks_per_beat': 480, 'tempo_bpm': 120, 'track_order': 'track_then_tick', 'fields': ['track', 'tick', 'note', 'velocity']}
PROBE_PATHS=['/app/output_data/provisional_checkpoint.json','/app/output_data/solution.py']
def digest(path):
    p=pathlib.Path(path); return hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else None
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--workspace',default='/app'); ap.add_argument('--output',default='/app/output_data/event_receipt.json'); args=ap.parse_args(); started=time.time()
    probes={p:digest(p) for p in PROBE_PATHS}
    payload={'schema_version':'async-rbench-event-receipt-v1','case_id':CASE_ID,'source_task_id':SOURCE_ID,'event':EVENT,'event_theme':EVENT_THEME,'meaning':MEANING,'authority':AUTHORITY,'worker_started_at':started,'worker_finished_at':time.time(),'worker_exit_code':0,'worker_output':'evaluator-owned authority completed','workspace_revision_before':digest('/app/output_data/provisional_checkpoint.json'),'workspace_revision_after':digest('/app/output_data/solution.py'),'probes':probes}
    payload['receipt_sha256']=hashlib.sha256(json.dumps(payload,sort_keys=True,separators=(',',':')).encode()).hexdigest(); out=pathlib.Path(args.output); out.parent.mkdir(parents=True,exist_ok=True); out.write_text(json.dumps(payload,indent=2,sort_keys=True)+'\n'); return 0
if __name__=='__main__': raise SystemExit(main())
