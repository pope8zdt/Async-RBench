from pathlib import Path
import json
import pytest
from async_rbench.main_experiment import load_main_cohort, make_manifest, validate_main_manifest

ROOT = Path(__file__).resolve().parents[1]

def test_main_cohort_is_the_user_selected_47_not_a_split():
    cohort = load_main_cohort(ROOT)
    assert cohort['case_count'] == len(cohort['instances']) == 47
    assert sum(cohort['theme_counts'].values()) == 47
    assert len(cohort['theme_counts']) == 8
    assert set(cohort['splits'].values()) == {'test', 'calibration', 'development'}
    assert cohort['repetitions'] * len(cohort['execution_modes']) * 47 == 282

def test_manifest_is_exactly_47_paired_cases():
    manifest = make_manifest(ROOT, model='example-model')
    assert len(manifest['episodes']) == 282
    assert {e['case_id'] + '::' + e['instance_id'] for e in manifest['episodes']} == set(load_main_cohort(ROOT)['instances'])
    assert manifest['paper_eval_selection']['cohort'] == 'formal-47'
    cohort = load_main_cohort(ROOT)
    validate_main_manifest(manifest, cohort)
    with pytest.raises(ValueError, match='282'):
        validate_main_manifest({**manifest, 'episodes':manifest['episodes'][:-1]}, cohort)
    with pytest.raises(ValueError, match='selection'):
        validate_main_manifest({**manifest, 'paper_eval_selection':{'cohort':'paper-eval-existing-61'}}, cohort)

def test_selection_tampering_fails_closed(tmp_path):
    target = tmp_path / 'experiments/formal-47'
    target.mkdir(parents=True)
    for name in ['cohort.json', 'instances.txt']:
        (target/name).write_bytes((ROOT/'experiments/formal-47'/name).read_bytes())
    with (target/'instances.txt').open('a') as f:
        f.write('unexpected::seed-1\n')
    with pytest.raises(ValueError, match='selection'):
        load_main_cohort(tmp_path)
