#!/usr/bin/env python3
import base64,hashlib,json,os
from pathlib import Path
m=os.sys.argv[1]; e=json.loads(base64.b64decode(os.environ['ASYNC_RBENCH_RESULT_PAYLOAD_B64']))['evidence']; R=Path('/app'); S=R/'task_file/environment_state.json'; O=R/'output_data'; h=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
if m=='partial': assert e['completion_id']=='sven-stockholm-matches-r1-partial' and e['status']=='partial' and e['matched_names']==['Stockholm Söder','Södermalm Delight'] and e['matched_ids']==['862457f415f0486a945965078f0a5a49','094330458b09419599085cbaa62d4999'] and e['unresolved_names']==['Stockholm Waterfront'] and e['source_sha256']==h(S)
elif m=='complete': assert e['completion_id']=='sven-stockholm-matches-r1-complete' and e['status']=='complete' and e['coverage']==['Stockholm Waterfront','Stockholm Söder','Södermalm Delight'] and e['saved_count']==3 and e['source_sha256']==h(S) and e['receipt_sha256']==h(R/'task_file/complete_match_receipt.json')
elif m=='comms': assert e['reply_within_deadline'] is True and e['fallback_message_count']==0 and e['ignored_email_ids']==['other-sender-stockholm','sven-uppsala'] and e['notification_count']==2 and e['source_sha256']==h(S)
elif m=='final': assert e['final_count']==3 and e['contact_sha256']==h(O/'contact.json') and e['communications_sha256']==h(O/'communications.json') and e['saved_sha256']==h(O/'saved_properties.json') and e['partial_sha256']==h(O/'partial_receipt.json')
else: raise AssertionError(m)
