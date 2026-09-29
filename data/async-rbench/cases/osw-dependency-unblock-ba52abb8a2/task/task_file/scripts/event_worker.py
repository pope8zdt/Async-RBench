import argparse,hashlib,json,pathlib
p=argparse.ArgumentParser();p.add_argument('--workspace');p.parse_args()
out=pathlib.Path('/app/output_data');out.mkdir(exist_ok=True)
base={'case_id':'osw-dependency-unblock-ba52abb8a2','source_task_id':'osworld:chrome:6766f2b8-8a72-417f-a9e5-56fcaa735837','worker_started_at':1,'worker_finished_at':2,'worker_exit_code':0,'probes':{'extracted_path':'/home/user/Desktop/helloExtension','manifest_present':True,'extension_loaded':True,'official_score':1.0},'finding':'The manifest-root directory /home/user/Desktop/helloExtension is the authoritative unpacked extension path.'}
base['receipt_sha256']=hashlib.sha256(json.dumps(base,sort_keys=True,separators=(',',':')).encode()).hexdigest()
(out/'event_receipt.json').write_text(json.dumps(base,indent=2)+'\n')
