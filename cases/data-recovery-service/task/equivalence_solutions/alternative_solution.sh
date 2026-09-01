#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json, sqlite3, pathlib, shutil, subprocess
from concurrent import futures
import pandas as pd
O=pathlib.Path('/app')
wal=O/'main.db-wal'; raw=wal.read_bytes()
if raw[:4] not in (b'\x37\x7f\x06\x82',b'\x37\x7f\x06\x83'):
    wal.write_bytes(bytes(x^0x42 for x in raw))
c=sqlite3.connect(O/'main.db'); rows=[dict(zip(('id','name','value'),r)) for r in c.execute('select id,name,value from items order by id')]; c.close()
(O/'recovered.json').write_text(json.dumps(rows,indent=2))
def norm(df, source):
    maps={'id':'user_id','full_name':'name','registration_date':'created_date','email_address':'email','created_at':'created_date','userId':'user_id','userName':'name','joined':'created_date','active':'status','is_active':'status'}
    df=df.rename(columns=maps)
    if 'status' in df and df.status.dtype==bool: df['status']=df.status.map({True:'active',False:'inactive'})
    return df.assign(_source=source)
a=norm(pd.DataFrame(json.loads((pathlib.Path('/data/source_a/users.json')).read_text())),'source_a')
b=norm(pd.read_csv('/data/source_b/users.csv'),'source_b'); c=norm(pd.read_parquet('/data/source_c/users.parquet'),'source_c')
all=pd.concat([a,b,c],ignore_index=True); fields=['name','email','created_date','status']; conflicts=[]
for uid,g in all.groupby('user_id'):
    g=g.sort_values('_source',key=lambda x:x.map({'source_a':0,'source_b':1,'source_c':2}))
    for f in fields:
        vals={r['_source']:str(r[f]) for r in g.to_dict('records') if f in g and pd.notna(r.get(f))}
        if len(set(vals.values()))>1: conflicts.append({'user_id':int(uid),'field':f,'values':vals,'selected':next(iter(vals.values()))})
merged=all.sort_values('_source',key=lambda x:x.map({'source_a':0,'source_b':1,'source_c':2})).groupby('user_id',as_index=False).first()
merged[['user_id','name','email','created_date','status']].to_parquet('/app/merged_users.parquet',index=False)
(O/'conflicts.json').write_text(json.dumps({'total_conflicts':len(conflicts),'conflicts':conflicts},indent=2))
proto='''syntax = "proto3"; service KVStore { rpc GetVal(GetValRequest) returns (GetValResponse); rpc SetVal(SetValRequest) returns (SetValResponse); } message GetValRequest { string key=1; } message GetValResponse { int32 val=1; } message SetValRequest { string key=1; int32 value=2; } message SetValResponse { int32 val=1; }'''
(O/'kv-store.proto').write_text(proto); subprocess.run(['python3','-m','grpc_tools.protoc','-I/app','--python_out=/app','--grpc_python_out=/app','/app/kv-store.proto'],check=True)
(O/'server.py').write_text("import json,grpc\nfrom concurrent import futures\nimport kv_store_pb2,kv_store_pb2_grpc\nclass Server(kv_store_pb2_grpc.KVStoreServicer):\n def __init__(self): self.kv_dict=json.load(open('/app/service_seed.json'))\n def GetVal(self,r,c): return kv_store_pb2.GetValResponse(val=self.kv_dict.get(r.key,0))\n def SetVal(self,r,c): self.kv_dict[r.key]=r.value; return kv_store_pb2.SetValResponse(val=r.value)\ns=grpc.server(futures.ThreadPoolExecutor(max_workers=4)); kv_store_pb2_grpc.add_KVStoreServicer_to_server(Server(),s); s.add_insecure_port('[::]:5328'); s.start(); s.wait_for_termination()\n")
seed={f"item:{r['name']}":int(r['value']) for r in rows}; seed.update({f"user:{int(r.user_id)}":1 if r.status=='active' else 0 for r in merged.itertuples()}); (O/'service_seed.json').write_text(json.dumps(seed,sort_keys=True))
sha=lambda p:__import__('hashlib').sha256(pathlib.Path(p).read_bytes()).hexdigest()
(O/'service-lineage.json').write_text(json.dumps({'recovered_sha256':sha('/app/recovered.json'),'merged_sha256':sha('/app/merged_users.parquet'),'seed_sha256':sha('/app/service_seed.json'),'recovered_row_count':len(rows)},sort_keys=True))
PY
nohup python3 /app/server.py >/tmp/grpc.log 2>&1 &
