"""Export allowlisted, non-ranked snapshots; never export raw benchmark traces."""
import argparse
import datetime
import hashlib
import json
from pathlib import Path

def number(value):
    return value if isinstance(value,(float,int)) and not isinstance(value,bool) else None

def project_result(source,digest,date):
    rows=source.get('rows',[])
    summary=source.get('development_summary') or {}
    themes=summary.get('theme_async_drs_scores',{}) or {}
    return {
        'id':digest[:16],'sourceSha256':digest,'date':date,
        'model':' / '.join(sorted(set(str(r.get('model','unknown')) for r in rows))) or 'Unspecified',
        'version':source.get('architecture_version','unknown'),
        'splits':sorted(set(str(r.get('split','unknown')) for r in rows)),
        'episodes':sum(r.get('n',0) for r in rows),'scored':sum(r.get('scored_n',0) for r in rows),
        'linear':number(summary.get('linear_base_task_score')),
        'async':number(summary.get('async_base_task_score')),
        'drs':number(summary.get('async_dynamic_replanning_score')),
        'pairedComplete':summary.get('paired_mode_coverage_complete') is True,
        'themeCount':len(themes),'themeScores':{str(k):number(v) for k,v in themes.items()},
        'linearMs':number((summary.get('wall_clock',{}).get('linear') or {}).get('duration_ms_mean')),
        'asyncMs':number((summary.get('wall_clock',{}).get('async') or {}).get('duration_ms_mean')),
        'published':False,'scope':'batch_diagnostic',
    }

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('benchmark_root',type=Path)
    parser.add_argument('--output',type=Path,default=Path('public/data/experiments.json'))
    args=parser.parse_args(); records={}
    for file in sorted((args.benchmark_root/'artifacts/experiments').glob('*/results.json')):
        raw=file.read_bytes()
        try: source=json.loads(raw)
        except (ValueError,UnicodeError): continue
        digest=hashlib.sha256(raw).hexdigest()
        date=datetime.datetime.fromtimestamp(file.stat().st_mtime,datetime.timezone.utc).isoformat()
        records[digest]=project_result(source,digest,date)
    output={'generatedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'source':'Local results.json snapshots; SHA-256 deduplicated. Not a combined benchmark ranking.','records':sorted(records.values(),key=lambda r:r['date'],reverse=True)}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(output,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'snapshots':len(records),'models':len(set(r['model'] for r in records.values()))}))

if __name__=='__main__':main()
