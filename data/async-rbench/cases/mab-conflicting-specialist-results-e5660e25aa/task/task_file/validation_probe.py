"""Public executable probes derived from the requested concurrency and SIGINT contract."""
import argparse,asyncio,hashlib,importlib.util,json,os,signal,subprocess,sys,tempfile,time
from pathlib import Path
p=argparse.ArgumentParser();p.add_argument('--output',default='/app/validation_report.json');p.add_argument('--handoff',action='store_true');a=p.parse_args()
module=Path('/app/run.py');module_hash=hashlib.sha256(module.read_bytes()).hexdigest()
spec=importlib.util.spec_from_file_location('candidate_run',module);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
async def normal():
 active=peak=started=finished=cleaned=0
 async def job():
  nonlocal active,peak,started,finished,cleaned
  active+=1;started+=1;peak=max(peak,active)
  try: await asyncio.sleep(.03);finished+=1
  finally: await asyncio.sleep(.02);active-=1;cleaned+=1
 await m.run_tasks([job]*4,2)
 assert (started,finished,cleaned,active)==(4,4,4,0),(started,finished,cleaned,active)
 assert peak==2,peak
 return {'started':started,'finished':finished,'cleaned':cleaned,'peak_concurrent':peak,'max_concurrent':2,'passed':True}
report={'implementation_sha256':module_hash,'probe_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),'completed_stages':[]}
report['normal']=asyncio.run(normal());report['completed_stages'].append('normal')
print('NORMAL_COMPLETE '+json.dumps(report,sort_keys=True),flush=True)
if a.handoff:
 print('AWAITING_STAGE_HANDOFF',flush=True)
 if sys.stdin.readline().strip()!='continue':raise RuntimeError('validation stage handoff was not received')
script=r"""import asyncio,sys
from run import run_tasks
async def job():
 try:
  print('STARTED',flush=True);await asyncio.sleep(30)
 finally:
  await asyncio.sleep(.12);print('CLEANED',flush=True)
asyncio.run(run_tasks([job]*int(sys.argv[1]),int(sys.argv[2])))
"""
checks=[]
for n,cap in ((2,3),(2,2),(3,2)):
 proc=subprocess.Popen([sys.executable,'-c',script,str(n),str(cap)],cwd='/app',stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,env={**os.environ,'PYTHONPATH':'/app'})
 time.sleep(.4);proc.send_signal(signal.SIGINT)
 try:stdout,stderr=proc.communicate(timeout=5)
 except subprocess.TimeoutExpired:proc.kill();stdout,stderr=proc.communicate();raise AssertionError('SIGINT cleanup timed out')
 wanted=min(n,cap);item={'n_tasks':n,'max_concurrent':cap,'started':stdout.splitlines().count('STARTED'),'cleaned':stdout.splitlines().count('CLEANED'),'returncode':proc.returncode}
 item['passed']=item['started']==wanted and item['cleaned']==wanted and proc.returncode in (0,-signal.SIGINT)
 assert item['passed'],{'measurement':item,'stdout':stdout,'stderr':stderr}
 checks.append(item)
report.update(interruption=checks,completed_stages=['normal','interrupt'])
assert hashlib.sha256(module.read_bytes()).hexdigest()==module_hash,'implementation changed during validation'
out=Path(a.output);out.parent.mkdir(parents=True,exist_ok=True);out.write_text(json.dumps(report,sort_keys=True)+'\n')
print('VALIDATION_COMPLETE '+json.dumps(report,sort_keys=True),flush=True)
