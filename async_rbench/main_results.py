"""Export only the fixed main-47 experiment, never raw traces or case scores."""
import argparse
from collections import defaultdict
import datetime
import hashlib
import json
import math
from pathlib import Path
from statistics import mean
from .main_experiment import load_main_cohort, validate_main_manifest, validate_bindings
from .evaluation.weighting import SCORE_POLICY_VERSION

def number(value):
    return value if isinstance(value, (float, int)) and not isinstance(value, bool) and math.isfinite(value) and 0 <= value <= 1 else None

def validate_score(score, episode, manifest_digest, manifest):
    for key in ['case_id', 'instance_id', 'episode_id', 'execution_mode', 'repeat', 'model', 'agent_seed', 'counterfactual_pair_id', 'guidance']:
        if score.get(key) != episode.get(key):
            raise ValueError('Score/manifest identity mismatch: ' + key)
    if score.get('manifest_sha256') != manifest_digest:
        raise ValueError('Score/manifest digest mismatch')
    for field in ['evaluation_contract_version', 'evaluation_contract_sha256']:
        if score.get(field) != manifest.get(field):
            raise ValueError('Score contract mismatch: ' + field)
    key = episode['case_id'] + '::' + episode['instance_id']
    for field, mapping in [('case_sha256', 'case_bundle_sha256'), ('verifier_bundle_sha256', 'verifier_bundle_sha256')]:
        if not score.get(field) or score[field] != manifest.get(mapping, {}).get(key):
            raise ValueError('Score case binding mismatch: ' + field)
    if score.get('score_status') == 'scored':
        if score.get('score_policy_version') != SCORE_POLICY_VERSION:
            raise ValueError('Incompatible score policy')
        if score.get('conformance_passed') is not True or score.get('protocol_valid') is not True or score.get('runtime_mode') != 'api_only':
            raise ValueError('Score does not satisfy main-experiment Track A gates')
        reasons = score.get('leaderboard_ineligibility_reasons', [])
        if not isinstance(reasons, list) or any(reason != 'split_not_test' for reason in reasons):
            raise ValueError('Score has a non-split eligibility failure')
        if score.get('leaderboard_eligible') is not True and reasons != ['split_not_test']:
            raise ValueError('Score has unexplained leaderboard ineligibility')

def add_episode(seen, key, score):
    if key in seen:
        raise ValueError('Duplicate main-experiment attempt; resolve source ambiguity before exporting')
    seen[key] = score

def aggregate_model(model, cohort, scores):
    keys = cohort['instances']
    modes = cohort['execution_modes']
    repetitions = range(cohort['repetitions'])
    expected = [(key, mode, repeat) for key in keys for mode in modes for repeat in repetitions]
    scored = {key: scores[key] for key in expected if scores.get(key, {}).get('score_status') == 'scored'}
    complete = []
    for key in keys:
        if all((key, mode, repeat) in scored
               and number(scored[(key, mode, repeat)].get('base_task_score')) is not None
               and (mode != 'async' or number(scored[(key, mode, repeat)].get('async_drs')) is not None)
               for mode in modes for repeat in repetitions):
            complete.append(key)
    def metric(mode, field):
        themes = defaultdict(list)
        for key in complete:
            themes[cohort['themes'][key]].append(mean(scored[(key, mode, repeat)][field] for repeat in repetitions))
        theme_means = {theme: mean(values) for theme, values in themes.items()}
        return (mean(theme_means.values()) if theme_means else None), theme_means
    linear, linear_themes = metric('linear', 'base_task_score')
    asynchronous, async_themes = metric('async', 'base_task_score')
    drs, themes = metric('async', 'async_drs')
    full = len(complete) == cohort['case_count']
    theme_metrics = {
        theme: {'linear': linear_themes.get(theme), 'async': async_themes.get(theme),
                'drs': themes.get(theme), 'caseCount': count,
                'completedCases': sum(cohort['themes'][key] == theme for key in complete)}
        for theme, count in cohort['theme_counts'].items()
    }
    resources = {}
    for mode in modes:
        mode_scores = [scored[(key, mode, repeat)] for key in complete for repeat in repetitions]
        resources[mode] = {}
        for output, field in [('tokens', 'total_tokens'), ('durationMs', 'episode_duration_ms')]:
            values = [s[field] for s in mode_scores if isinstance(s.get(field), (int, float))
                      and not isinstance(s[field], bool) and math.isfinite(s[field]) and s[field] >= 0]
            resources[mode][output] = {'mean': mean(values) if values else None,
                                      'measuredEpisodes': len(values)}
    return {
        'id': hashlib.sha256((cohort['id'] + ':' + model).encode()).hexdigest()[:16],
        'model': model, 'version': cohort['evaluation_contract_version'], 'scope': 'main_experiment_47',
        'caseCount': cohort['case_count'], 'completedCases': len(complete),
        'episodes': len(expected), 'scored': len(scored),
        'linear': linear if full else None, 'async': asynchronous if full else None, 'drs': drs if full else None,
        'observedLinear': linear, 'observedAsync': asynchronous, 'observedDrs': drs,
        'pairedComplete': full, 'themeCount': len(themes), 'themeScores': themes,
        'themeMetrics': theme_metrics, 'resources': resources,
        'coverageStatus': 'complete' if full else 'incomplete',
        'executionStatus': 'unknown', 'reviewStatus': 'self_reported',
        'published': False,
    }

def read_experiments(root, cohort, manifest_paths=None):
    selected = set(cohort['instances'])
    scores = {model: {} for model in cohort['models']}
    evidence = {model: [] for model in cohort['models']}
    dates = {model: [] for model in cohort['models']}
    for file in sorted(manifest_paths if manifest_paths is not None else (root / 'artifacts/experiments').glob('*/manifest.json')):
        raw = file.read_bytes()
        manifest = json.loads(raw)
        model = manifest.get('model')
        if model not in scores:
            continue
        declared = manifest.get('paper_eval_selection', {}).get('cohort') == cohort['id']
        legacy_batch = file.parent.name.startswith('batch-' + model + '-')
        if not (declared or legacy_batch):
            continue
        episodes = manifest.get('episodes', [])
        chosen = [e for e in episodes if e['case_id'] + '::' + e['instance_id'] in selected]
        if not chosen:
            continue
        if any(manifest.get(key) != cohort[key] for key in ['repetitions', 'seed', 'guidance']):
            raise ValueError('Main-experiment settings do not match the fixed cohort')
        if declared and {e['case_id'] + '::' + e['instance_id'] for e in episodes} != selected:
            raise ValueError('Declared main-47 manifest has different membership')
        if declared and manifest['paper_eval_selection'].get('selection_sha256') != cohort['selection_sha256']:
            raise ValueError('Declared main-47 manifest has a different selection digest')
        if declared:
            validate_main_manifest(manifest, cohort)
        validate_bindings(manifest, cohort, chosen)
        digest = hashlib.sha256(raw).hexdigest()
        evidence[model].append(digest)
        for episode in chosen:
            if episode.get('model') != model:
                raise ValueError('Episode model differs from its main-experiment manifest')
            key = (episode['case_id'] + '::' + episode['instance_id'], episode['execution_mode'], episode['repeat'])
            if key[1] not in cohort['execution_modes'] or key[2] not in range(cohort['repetitions']):
                raise ValueError('Unexpected main-experiment mode or repeat')
            episode_id = episode['episode_id']
            if '/' in episode_id or '\\' in episode_id or episode_id in ('.', '..'):
                raise ValueError('Invalid episode identifier')
            path = file.parent / 'runs' / episode_id / 'score.json'
            if path.is_file():
                raw_score = path.read_bytes()
                score = json.loads(raw_score)
                validate_score(score, episode, digest, manifest)
                evidence[model].append(hashlib.sha256(raw_score).hexdigest())
                dates[model].append(path.stat().st_mtime)
            else:
                score = {}
            add_episode(scores[model], key, score)
    # Pair configuration and evaluator must agree even when sources span manifests.
    for model_scores in scores.values():
        pairs = {}
        for (key, mode, repeat), score in model_scores.items():
            if not score or score.get('score_status') != 'scored':
                continue
            fields = ['agent_seed', 'counterfactual_pair_id', 'case_sha256', 'verifier_bundle_sha256',
                      'resource_policy_sha256', 'scaffold_and_protocol_sha256']
            binding = tuple(score.get(field) for field in fields)
            if any(value is None for value in binding):
                raise ValueError('Missing pair configuration binding')
            pair = (key, repeat)
            if pair in pairs and pairs[pair] != binding:
                raise ValueError('Incompatible paired score configuration')
            pairs[pair] = binding
    return scores, evidence, dates

def export(root, manifest_path=None, *, cohort_root=None):
    cohort = load_main_cohort(cohort_root or root)
    if manifest_path is not None:
        manifest = json.loads(manifest_path.read_bytes())
        validate_main_manifest(manifest, cohort)
        cohort = {**cohort, 'models': [manifest['model']]}
    scores, evidence, dates = read_experiments(root, cohort, [manifest_path] if manifest_path is not None else None)
    records = []
    for model in cohort['models']:
        record = aggregate_model(model, cohort, scores[model])
        record['sourceSha256'] = hashlib.sha256((cohort['selection_sha256'] + ''.join(sorted(evidence[model]))).encode()).hexdigest()
        record['date'] = datetime.datetime.fromtimestamp(max(dates[model]), datetime.timezone.utc).isoformat() if dates[model] else None
        records.append(record)
    return {
        'generatedAt': datetime.datetime.now(datetime.timezone.utc).isoformat(),
        'source': 'Main-47 manifest-bound episode scores. Historical splits do not filter this cohort.',
        'cohort': {key: cohort[key] for key in ['id', 'case_count', 'selection_sha256', 'repetitions', 'theme_counts', 'models']},
        'records': records,
    }

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('benchmark_root', type=Path)
    parser.add_argument('--output', type=Path, default=Path('public/data/experiments.json'))
    parser.add_argument('--manifest', type=Path, help='Summarize one declared main-47 run, including participant models')
    args = parser.parse_args()
    data = export(args.benchmark_root.resolve(), args.manifest)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2, allow_nan=False), encoding='utf-8')
    print(json.dumps({'cohort': data['cohort']['id'], 'cases': data['cohort']['case_count'],
                     'models': [{k:r[k] for k in ['model', 'completedCases', 'scored', 'episodes']} for r in data['records']]}))

if __name__ == '__main__': main()
