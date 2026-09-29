#!/usr/bin/env python3
import base64,hashlib,json,os
from pathlib import Path
mode=os.sys.argv[1]; e=json.loads(base64.b64decode(os.environ['ASYNC_RBENCH_RESULT_PAYLOAD_B64']))['evidence']; R=Path('/app'); P=R/'task_file/corpus_plan.json'; h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
if mode=='shard':
 a=json.loads((R/'task_file/shard_017_authority_receipt.json').read_text()); assert e['completion_id']==a['completion_id'] and e['shard_id']=='shard-017' and e['source_revision']==a['source_revision'] and (e['start'],e['stop'],e['row_count'])==(16000,17200,1200) and e['payload_sha256']==a['payload_sha256'] and e['receipt_sha256']==h(R/'task_file/shard_017_authority_receipt.json')
elif mode=='corpus': assert e['row_count']==e['unique_example_ids']==93347 and e['locale']=='es' and e['required_fields']==['example_id','query','esci_label','product_locale','product_title'] and e['choices']==['E','S','C','I'] and e['plan_sha256']==h(P)
elif mode=='replay': assert e['completion_id']=='esci-export-shard-017' and e['delivery_count']==2 and e['contribution_count']==1 and e['disposition']=='ignored_duplicate_completion' and e['plan_sha256']==h(P)
elif mode=='final':
 assert e['disposition']=='ignored_duplicate_completion' and e['dataset_sha256']==h(R/'esci.jsonl') and e['config_sha256']==h(R/'escitask/esci.yaml') and e['manifest_sha256']==h(R/'integration_manifest.json')
else: raise AssertionError(mode)
