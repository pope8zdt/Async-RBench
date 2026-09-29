#!/usr/bin/env python3
import base64,hashlib,json,os
from pathlib import Path
mode=os.sys.argv[1]; e=json.loads(base64.b64decode(os.environ['ASYNC_RBENCH_RESULT_PAYLOAD_B64']))['evidence']; R=Path('/app'); P=R/'task_file/maze_plan.json'; h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest(); plan=json.loads(P.read_text())
if mode=='batch':
 a=json.loads((R/'task_file/batch_01_03_authority_receipt.json').read_text()); assert e['completion_id']==a['completion_id'] and e['maze_ids']==[1,2,3] and e['source_revision']==a['source_revision'] and e['map_sha256']==a['map_sha256'] and e['receipt_sha256']==h(R/'task_file/batch_01_03_authority_receipt.json')
elif mode=='maps': assert e['maze_ids']==list(range(1,11)) and e['map_count']==10 and e['plan_sha256']==h(P)
elif mode=='replay': assert e['completion_id']=='maze-batch-01-03' and e['delivery_count']==2 and e['contribution_count']==1 and e['disposition']=='ignored_duplicate_completion' and e['plan_sha256']==h(P)
elif mode=='final':
 assert e['disposition']=='ignored_duplicate_completion' and e['manifest_sha256']==h(R/'integration_manifest.json') and e['map_sha256']=={str(i):h(R/f'output/{i}.txt') for i in range(1,11)}
else: raise AssertionError(mode)
