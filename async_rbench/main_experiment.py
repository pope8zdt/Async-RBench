"""The fixed main-experiment cohort. Historical dataset splits are metadata."""
from __future__ import annotations

import argparse
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path

COHORT_DIRECTORY = Path('experiments/formal-47')

def load_main_cohort(root: Path) -> dict:
    directory = root / COHORT_DIRECTORY
    cohort = json.loads((directory / 'cohort.json').read_text(encoding='utf-8'))
    keys = (directory / 'instances.txt').read_text(encoding='utf-8-sig').splitlines()
    canonical = '\n'.join(keys) + '\n'
    if (len(keys) != 47 or len(set(keys)) != 47 or cohort['case_count'] != 47
            or hashlib.sha256(canonical.encode()).hexdigest() != cohort['selection_sha256']):
        raise ValueError('main experiment selection must match the fixed 47-case digest')
    with (root / 'experiments/formal-61/paper-eval-existing-61.csv').open(encoding='utf-8', newline='') as f:
        reference = {row['case_id'] + '::' + row['instance_id']: row for row in csv.DictReader(f)}
    if not set(keys) <= set(reference):
        raise ValueError('main experiment selection contains unknown instances')
    themes = {key: reference[key]['theme'] for key in keys}
    if dict(Counter(themes.values())) != cohort['theme_counts'] or len(cohort['theme_counts']) != 8:
        raise ValueError('main experiment theme coverage differs from the frozen selection')
    if cohort['repetitions'] != 3 or cohort['execution_modes'] != ['linear', 'async']:
        raise ValueError('main experiment requires three paired repetitions')
    contract = (root / 'evaluation_contract.json').read_bytes()
    return {**cohort, 'instances': keys, 'themes': themes,
            'evaluation_contract_version': json.loads(contract)['version'],
            'evaluation_contract_sha256': hashlib.sha256(contract).hexdigest(),
            'splits': {key: reference[key]['split'] for key in keys}}

def make_manifest(root: Path, *, model: str) -> dict:
    from .evaluation.manifest import create_manifest
    cohort = load_main_cohort(root)
    if root.resolve() != Path(__file__).resolve().parents[1]:
        raise ValueError('manifest creation must target this repository root')
    manifest = create_manifest([key.split('::')[0] for key in cohort['instances']],
        cohort['repetitions'], cohort['guidance'], cohort['seed'],
        execution_modes=cohort['execution_modes'], instance_keys=cohort['instances'], model=model)
    manifest['paper_eval_selection'] = {
        'cohort': cohort['id'], 'case_count': 47, 'selection_file': cohort['selection_file'],
        'selection_sha256': cohort['selection_sha256'],
    }
    return manifest

def validate_main_manifest(manifest: dict, cohort: dict) -> None:
    selection = manifest.get('paper_eval_selection', {})
    if selection.get('cohort') != cohort['id'] or selection.get('selection_sha256') != cohort['selection_sha256']:
        raise ValueError('manifest does not belong to the fixed main-47 selection')
    if any(manifest.get(key) != cohort[key] for key in ['repetitions', 'seed', 'guidance']):
        raise ValueError('manifest settings differ from the fixed main-47 plan')
    expected = {(key, mode, repeat) for key in cohort['instances']
                for mode in cohort['execution_modes'] for repeat in range(cohort['repetitions'])}
    episodes = manifest.get('episodes', [])
    actual = [(e['case_id'] + '::' + e['instance_id'], e['execution_mode'], e['repeat']) for e in episodes]
    if len(actual) != len(expected) or set(actual) != expected:
        raise ValueError('manifest must contain exactly the 282 main-47 episode slots')
    if any(e.get('model') != manifest.get('model') for e in episodes):
        raise ValueError('manifest episode model mismatch')
    validate_bindings(manifest, cohort, episodes)

def validate_bindings(manifest: dict, cohort: dict, episodes: list) -> None:
    for field in ['evaluation_contract_version', 'evaluation_contract_sha256']:
        if manifest.get(field) != cohort[field]:
            raise ValueError('manifest contract mismatch: ' + field)
    pairs = {}
    for episode in episodes:
        if episode.get('guidance') != cohort['guidance']:
            raise ValueError('episode guidance mismatch')
        if not isinstance(episode.get('agent_seed'), int) or not episode.get('counterfactual_pair_id'):
            raise ValueError('missing pair binding')
        key = (episode['case_id'], episode['instance_id'], episode['repeat'])
        binding = (episode['agent_seed'], episode['counterfactual_pair_id'])
        if key in pairs and pairs[key] != binding:
            raise ValueError('Linear/Async pair binding mismatch')
        pairs[key] = binding

def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Main 47-case paired experiment')
    sub = parser.add_subparsers(dest='command', required=True)
    for command in ['check', 'make-manifest', 'check-manifest']:
        p = sub.add_parser(command)
        p.add_argument('--root', type=Path, default=Path.cwd())
        if command == 'check-manifest':
            p.add_argument('--manifest', type=Path, required=True)
        if command == 'make-manifest':
            p.add_argument('--output', type=Path, required=True)
            p.add_argument('--model', required=True)
            p.add_argument('--repetitions', type=int, choices=[3], default=3)
            p.add_argument('--guidance', choices=['incentive'], default='incentive')
            p.add_argument('--seed', type=int, choices=[2026], default=2026)
    args = parser.parse_args(argv)
    cohort = load_main_cohort(args.root)
    if args.command == 'check-manifest':
        validate_main_manifest(json.loads(args.manifest.read_text(encoding='utf-8')), cohort)
    if args.command == 'make-manifest':
        from .evaluation.manifest import write_manifest
        write_manifest(args.output.resolve(), make_manifest(args.root, model=args.model))
    print(json.dumps({'cohort': cohort['id'], 'case_count': 47, 'episodes_per_model': 282,
                      'selection_sha256': cohort['selection_sha256']}))
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
