"""Preview or write a sanitized main-experiment snapshot from an authorized local checkout."""
import argparse
import json
from pathlib import Path
import sys
import tempfile

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from async_rbench.main_results import export


def refresh(runs_root, *, write=False):
    # Cohort policy is the website checkout's committed selection; inputs may live elsewhere.
    data=export(Path(runs_root).resolve(),cohort_root=ROOT)
    target=ROOT/'website/public/data/experiments.json'
    if write:
        target.parent.mkdir(parents=True,exist_ok=True)
        with tempfile.NamedTemporaryFile(mode='w',encoding='utf-8',dir=target.parent,suffix='.tmp',delete=False) as f:
            path=Path(f.name)
            json.dump(data,f,ensure_ascii=False,indent=2,allow_nan=False)
            f.write('\n')
        try: path.replace(target)
        finally: path.unlink(missing_ok=True)
    return {'written':write,'generatedAt':data['generatedAt'],'cohort':data['cohort']['id'],
            'records':[{k:r[k] for k in ['model','completedCases','scored','episodes','executionStatus']} for r in data['records']]}

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--runs-root',type=Path,default=ROOT)
    parser.add_argument('--write',action='store_true',help='Write public snapshot; does not commit or publish')
    args=parser.parse_args()
    print(json.dumps(refresh(args.runs_root,write=args.write),ensure_ascii=False))
