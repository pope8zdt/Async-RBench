#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import hashlib,json,os
from pathlib import Path
t=Path('/app/task_file'); o=Path('/app/output_data'); (o).mkdir(exist_ok=True)
saved=json.loads((t/'app/raf_saved_list.json').read_text()); catalog=json.loads((t/'app/raf_catalog.json').read_text()); contacts=json.loads((t/'app/contacts.json').read_text())
prefs=saved['search_preferences']; original={x['id'] for x in saved['saved']}
def match(x): return x['city']==prefs['city'] and prefs['min_rent_sek']<=x['price_sek']<=prefs['max_rent_sek']
kept={x['id']:dict(x) for x in saved['saved'] if x['city']!=prefs['city'] or match(x)}
removed=[x['id'] for x in saved['saved'] if x['id'] not in kept]
added=[]
for x in catalog['catalog']:
    if match(x) and x['id'] not in original: kept[x['id']]=dict(x); added.append(x['id'])
plan={'initial_plan':{'corrected_saved_ids':list(kept),'removed_ids':removed,'added_ids':added},'planned_saved_ids':list(kept)}
(o/'planned_ops.json').write_text(json.dumps(plan,indent=2))
events=[json.loads(x) for x in (t/'event_feed/feed.jsonl').read_text().splitlines() if x.strip()]; events.sort(key=lambda x:x['seq'])
notes=[]; observed=[]
for e in events:
    x=e['listing']; yes=match(x); row={'seq':e['seq'],'listing_id':x['id'],'at':e['at'],'matched':yes,'disposition':'added_and_notified' if yes else 'ignored','reason':'in-range saved-search match' if yes else 'outside saved-search'}
    observed.append(row)
    if yes:
        kept[x['id']]=dict(x); notes.append({'seq':e['seq'],'recipient':contacts['contacts'][0]['name'],'listing_id':x['id'],'apartment':x['name'],'price_sek':x['price_sek'],'at':e['at']})
final={'owner':saved['owner'],'search_preferences':prefs,'saved':list(kept.values())}
(o/'saved_list_final.json').write_text(json.dumps(final,indent=2)); (o/'notifications.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in notes))
feed=(t/'event_feed/feed.jsonl').read_bytes(); report={'feed':'/app/task_file/event_feed/feed.jsonl','window_minutes':json.loads((t/'event_feed/feed_meta.json').read_text())['window_minutes'],'stream_revision':hashlib.sha256(feed).hexdigest(),'observed_events':observed,'window_closed':True,'final_saved_ids':list(kept),'notifications_sent':[x['listing_id'] for x in notes]}
(o/'event_monitor_report.json').write_text(json.dumps(report,indent=2))
PY
python3 /app/task_file/scripts/write_manifest.py
