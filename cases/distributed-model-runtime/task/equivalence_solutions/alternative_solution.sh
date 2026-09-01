#!/usr/bin/env bash
set -euo pipefail
python3 - <<'PY'
import json,pathlib,hashlib,math,torch
import torch.nn as nn
import torch.nn.functional as F
O=pathlib.Path('/app'); T=O/'task_file'
class P(nn.Module):
 def __init__(self,d):
  super().__init__(); x=torch.zeros(5000,d); q=torch.arange(5000).float().unsqueeze(1); z=torch.exp(torch.arange(0,d,2).float()*(-math.log(10000)/d)); x[:,0::2]=torch.sin(q*z); x[:,1::2]=torch.cos(q*z); self.register_buffer('pe',x.unsqueeze(0))
 def forward(self,x): return x+self.pe[:,:x.size(1)]
class M(nn.Module):
 def __init__(self):
  super().__init__(); self.embedding=nn.Linear(64,128); self.pos_encoder=P(128); self.transformer_encoder=nn.TransformerEncoder(nn.TransformerEncoderLayer(128,4,256,dropout=0),3); self.transformer_decoder=nn.TransformerDecoder(nn.TransformerDecoderLayer(128,4,256,dropout=0),1); self.output_layer=nn.Linear(128,64)
 def forward(self,a,b): return self.output_layer(self.transformer_decoder(self.pos_encoder(self.embedding(b)),self.transformer_encoder(self.pos_encoder(self.embedding(a)))))
m=M(); m.load_state_dict(torch.load('/app/weights.pt')); d=torch.load('/app/dataset.pt'); o=torch.optim.Adam(m.output_layer.parameters(),lr=.001)
for _ in range(10): o.zero_grad(); l=F.mse_loss(m(d['src_sequences'],d['tgt_sequences']),d['tgt_sequences']); l.backward(); o.step()
torch.jit.trace(
 m.eval(),
 (d['src_sequences'][:1], d['tgt_sequences'][:1]),
 strict=False,
).save('/app/model.pt')
(O/'pipeline_parallel.py').write_text('''import torch
import torch.distributed as dist
import torch.nn as nn
import torch.nn.functional as F
def train_step_pipeline_afab(model,inputs,targets,device,dtype):
 r=dist.get_rank(); w=dist.get_world_size(); b=model.model; n=len(b.layers); q=[n//w+(i<n%w) for i in range(w)]; s=sum(q[:r]); b.layers=nn.ModuleList(b.layers[s:s+q[r]])
 if r: b.embed_tokens=nn.Identity()
 if r<w-1: b.norm=nn.Identity(); model.lm_head=nn.Identity()
 for i,x in enumerate(inputs):
  if r: x=torch.empty(x.shape[0],x.shape[1],model.config.hidden_size,device=device,dtype=dtype,requires_grad=True); dist.recv(x,r-1)
  y=model(x.to(device))[0]
  if r<w-1: dist.send(y.detach(),r+1)
  elif y.requires_grad: F.cross_entropy(y.view(-1,y.size(-1)),targets[i].to(device).view(-1),ignore_index=-100).backward()
''')
def R(b): return [json.loads(x) for x in (T/'input_data'/f'requests_bucket_{b}.jsonl').read_text().splitlines() if x]
S=sorted({((int(x['prompt_len'])+63)//64)*64 for x in R(1)+R(2)}); reps=[S[min(len(S)-1,round(i*(len(S)-1)/7))] for i in range(min(8,len(S)))]
import sys
sys.path.insert(0,str(T/'scripts'))
from cost_model import CostModel
cm=CostModel(64)
limits={
 1:{'cost':3e11,'pad_ratio':.055,'p95_latency_ms':2.1e6,'sequential_timecost':2.7e8},
 2:{'cost':4.8e10,'pad_ratio':.15,'p95_latency_ms':2.1e5,'sequential_timecost':3.2e7},
}
def shape_for(request):
 aligned=((int(request['prompt_len'])+63)//64)*64
 return next((value for value in reps if value>=aligned),reps[-1])
def build_plan(bucket):
 requests=R(bucket); index={item['request_id']:item for item in requests}; grouped={}
 for item in requests:
  grouped.setdefault(shape_for(item),{}).setdefault(int(item['gen_len']),[]).append(item)
 groups={shape:[rows for _,rows in sorted(by_generation.items())] for shape,by_generation in grouped.items()}
 def emit():
  rows=[]; sequence=0
  for shape in sorted(groups):
   for batch in groups[shape]:
    sequence+=1
    for item in batch:
     rows.append({'request_id':item['request_id'],'batch_id':f'alt-{bucket}-{sequence:04d}','shape':{'seq_align':shape,'heads_align':32,'hidden_align':4096}})
  return rows
 def metrics(): return cm.plan_metrics(index,emit())
 current=metrics()
 while current['sequential_timecost']>limits[bucket]['sequential_timecost']:
  candidates=[]
  for shape,batches in groups.items():
   for position in range(len(batches)-1):
    left,right=batches[position:position+2]
    lm,rm,merged=cm.batch_metrics(left),cm.batch_metrics(right),cm.batch_metrics(left+right)
    extra_cost=merged['cost']-lm['cost']-rm['cost']-cm.c.Kbatch_overhead_cost
    saved_time=(max(lm['latencies'])+8)+(max(rm['latencies'])+8)-(max(merged['latencies'])+8)
    extra_pad=merged['pad_tokens']-lm['pad_tokens']-rm['pad_tokens']
    if saved_time>0: candidates.append((extra_cost/saved_time,extra_cost,extra_pad,-saved_time,shape,position))
  accepted=False
  for _,_,_,_,shape,position in sorted(candidates):
   previous=groups[shape][position:position+2]
   groups[shape][position:position+2]=[previous[0]+previous[1]]
   trial=metrics()
   if all(trial[name]<=limits[bucket][name] for name in ('cost','pad_ratio','p95_latency_ms')):
    current=trial; accepted=True; break
   groups[shape][position:position+1]=previous
  if not accepted: raise RuntimeError(f'cannot satisfy bucket {bucket} thresholds')
 return emit()
for b in (1,2):
 out=build_plan(b)
 (T/'output_data').mkdir(exist_ok=True)
 (T/'output_data'/f'plan_b{b}.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in out))
h=lambda p:hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
d={'backend':'pipeline','profile_version':'v2','world_size':2,'model_sha256':h('/app/model.pt'),'implementation_sha256':h('/app/pipeline_parallel.py'),'plan_b1_sha256':h('/app/task_file/output_data/plan_b1.jsonl'),'plan_b2_sha256':h('/app/task_file/output_data/plan_b2.jsonl')}
(O/'deployment.json').write_text(json.dumps(d)); (O/'batch-lineage.json').write_text(json.dumps({'backend':'pipeline','profile_version':'v2','plan_b1_sha256':d['plan_b1_sha256'],'plan_b2_sha256':d['plan_b2_sha256']}))
PY

cp /async_rbench/upstream_solutions/alternative_parallel_linear.py /app/parallel_linear.py
cp /async_rbench/upstream_solutions/alternative_pipeline_parallel.py /app/pipeline_parallel.py
python3 - <<'PY'
import hashlib, json
from pathlib import Path
path = Path('/app/deployment.json')
deployment = json.loads(path.read_text())
deployment['implementation_sha256'] = hashlib.sha256(Path('/app/pipeline_parallel.py').read_bytes()).hexdigest()
path.write_text(json.dumps(deployment, sort_keys=True, indent=2))
PY
