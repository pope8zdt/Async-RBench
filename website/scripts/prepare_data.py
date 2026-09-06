"""Generate public corpus metadata and merge explicitly reviewed submissions."""
import argparse
import json
from pathlib import Path
import re
import sys

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from async_rbench.main_experiment import load_main_cohort
from async_rbench.submissions import (
    COHORT_FIELDS, RECORD_FIELDS, OPTIONAL_RECORD_FIELDS,
    _canonical, _digest, _object, _read, _text, _timestamp,
    load_accepted, validate_record,
)
from catalog import build_catalog

SNAPSHOT_FIELDS = {'generatedAt', 'source', 'cohort', 'records'}
SNAPSHOT_COHORT_FIELDS = COHORT_FIELDS | {'models'}
LEGACY_STATUS_FIELDS = {'coverageStatus', 'executionStatus', 'reviewStatus'}


def validate_snapshot(snapshot, cohort):
    """Return allowlisted snapshot data; validation is not score attestation."""
    _object(snapshot, SNAPSHOT_FIELDS, label='main result snapshot')
    _timestamp(snapshot['generatedAt'])
    _text(snapshot['source'], 'snapshot source')
    _object(snapshot['cohort'], SNAPSHOT_COHORT_FIELDS, label='snapshot cohort')
    expected_cohort = {key: cohort[key] for key in SNAPSHOT_COHORT_FIELDS}
    if _canonical(snapshot['cohort']) != _canonical(expected_cohort):
        raise ValueError('Main result snapshot differs from fixed 47-case cohort')
    if not isinstance(snapshot['records'], list):
        raise ValueError('Main result snapshot records must be a list')
    records = []
    models = set()
    for source in snapshot['records']:
        _object(source, (RECORD_FIELDS - LEGACY_STATUS_FIELDS) | {'id'},
                OPTIONAL_RECORD_FIELDS | LEGACY_STATUS_FIELDS, 'snapshot record')
        _digest(source['id'], 16)
        _text(source['model'], 'snapshot model')
        if source['model'] not in cohort['models'] or source['model'] in models:
            raise ValueError('Unexpected or duplicate model in main experiment snapshot')
        models.add(source['model'])
        record = {key: source[key] for key in sorted(RECORD_FIELDS | OPTIONAL_RECORD_FIELDS) if key in source}
        # Older exporter snapshots omit these statuses. Supplied assertions must
        # still pass validation; filling missing fields cannot promote trust.
        record.setdefault('coverageStatus', 'complete' if source['pairedComplete'] is True else 'incomplete')
        record.setdefault('executionStatus', 'unknown')
        record.setdefault('reviewStatus', 'self_reported')
        validate_record(record, cohort)
        records.append({'id': source['id'], **record})
    if models != set(cohort['models']):
        raise ValueError('Main experiment snapshot must represent every panel model')
    return {'generatedAt': snapshot['generatedAt'], 'source': snapshot['source'],
            'cohort': {key: expected_cohort[key] for key in sorted(SNAPSHOT_COHORT_FIELDS)},
            'records': records}


def prepare(root=ROOT):
    root=Path(root)
    cohort=load_main_cohort(root)
    snapshot=validate_snapshot(_read(root/'website/public/data/experiments.json'), cohort)
    records=list(snapshot['records'])
    records.extend(load_accepted(root))
    ids=set()
    for record in records:
        if not re.fullmatch(r'[a-f0-9]{16}|[a-f0-9]{64}',record['id']) or record['id'] in ids:
            raise ValueError('Invalid or duplicate public result identifier')
        ids.add(record['id'])
    corpus=build_catalog(root)
    leaderboard={'generatedAt':snapshot['generatedAt'], 'source':snapshot['source'],
                 'cohort':snapshot['cohort'], 'records':records, 'builtAt':corpus['generatedAt']}
    target=root/'website/public/data'
    target.mkdir(parents=True,exist_ok=True)
    for name,value in [('corpus.json',corpus),('leaderboard.json',leaderboard)]:
        (target/name).write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n',encoding='utf-8')
    return {'caseCount':corpus['caseCount'],'instanceCount':corpus['instanceCount'],
            'mainRecords':len(snapshot['records']),'acceptedSubmissions':len(records)-len(snapshot['records'])}

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,default=ROOT)
    args=parser.parse_args();print(json.dumps(prepare(args.root)))
