"""Count one source log. This tool contains no reference answer or event policy."""
import hashlib, json, sys
from pathlib import Path
name=sys.argv[1]
assert name in {'app1.log','app2.log','db.log'}
p=Path('/app/logs')/name; data=p.read_bytes()
report={'source_file':name,'source_sha256':hashlib.sha256(data).hexdigest(),'counts':{s:sum(s in line for line in data.decode().splitlines()) for s in ('ERROR','WARNING','INFO')}}
out=Path('/app/shards')/(name+'.json'); out.parent.mkdir(exist_ok=True)
out.write_text(json.dumps(report,sort_keys=True)+'\n')
print(json.dumps({'evidence':{**report,'report_path':str(out)},'files':[str(out)]}))
