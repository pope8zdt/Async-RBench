"""Submission trust boundaries; no model execution or third-party dependencies."""
import copy
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from async_rbench.main_experiment import load_main_cohort
from async_rbench import submissions

ROOT = Path(__file__).resolve().parents[1]


class SubmissionTests(unittest.TestCase):
    def setUp(self):
        self.cohort = load_main_cohort(ROOT)
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        for name in ['experiments/formal-47', 'experiments/formal-61']:
            shutil.copytree(ROOT / name, self.root / name)
        shutil.copyfile(ROOT / 'evaluation_contract.json', self.root / 'evaluation_contract.json')
        self.record = {
            'id': 'legacy-model-id', 'model': 'participant/model',
            'version': self.cohort['evaluation_contract_version'], 'scope': 'main_experiment_47',
            'caseCount': 47, 'completedCases': 47, 'episodes': 282, 'scored': 282,
            'linear': .5, 'async': .6, 'drs': .7,
            'observedLinear': .5, 'observedAsync': .6, 'observedDrs': .7,
            'pairedComplete': True, 'themeCount': 8,
            'themeScores': {key: .7 for key in self.cohort['theme_counts']},
            'published': False, 'sourceSha256': 'a' * 64, 'date': None,
        }

    def tearDown(self):
        self.temp.cleanup()

    def package(self, source='a'):
        record = {**self.record, 'sourceSha256': source * 64}
        with patch('async_rbench.main_results.export', return_value={'records': [record]}):
            return submissions.package_run(self.root, self.root / 'manifest.json', benchmark_commit='b' * 40)

    def reseal(self, package):
        content = {k: v for k, v in package.items() if k not in ['submissionId', 'contentSha256']}
        digest = hashlib.sha256(json.dumps(content, sort_keys=True, separators=(',', ':'), ensure_ascii=False, allow_nan=True).encode()).hexdigest()
        package.update(submissionId=digest, contentSha256=digest)
        return package

    def save(self, package):
        directory = self.root / 'submissions/entries'
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / (package['submissionId'] + '.json')
        target.write_text(json.dumps(package), encoding='utf-8')
        return target

    def review(self, package, **changes):
        review = {'schemaVersion': 1, 'submissionId': package['submissionId'],
                  'contentSha256': package['contentSha256'], 'reviewStatus': 'materials_reviewed',
                  'reviewer': 'Maintainer', 'reviewedAt': '2026-09-06T12:00:00+00:00', 'evidenceUrl': None}
        review.update(changes)
        directory = self.root / 'submissions/reviews'
        directory.mkdir(parents=True, exist_ok=True)
        (directory / (package['submissionId'] + '.json')).write_text(json.dumps(review), encoding='utf-8')

    def test_deterministic_allowlisted_package(self):
        self.record['privateTrace'] = 'MUST NEVER EXPORT'
        first, second = self.package(), self.package()
        self.assertEqual(first, second)
        self.assertNotIn('privateTrace', json.dumps(first))
        submissions.validate_submission(first, self.cohort)
        self.assertEqual(first['record']['reviewStatus'], 'self_reported')

    def test_config_only_hash_and_distinct_runs(self):
        config = self.root / 'private.json'
        config.write_bytes(b'{"secret":"DO NOT EXPORT"}')
        with patch('async_rbench.main_results.export', return_value={'records': [self.record]}):
            package = submissions.package_run(self.root, self.root / 'manifest.json', benchmark_commit='b' * 40, config_path=config)
        self.assertEqual(package['configSha256'], hashlib.sha256(config.read_bytes()).hexdigest())
        self.assertNotIn('DO NOT EXPORT', json.dumps(package))
        self.assertNotEqual(self.package()['submissionId'], self.package('c')['submissionId'])

    def test_tampering_and_wrong_cohort(self):
        package = self.package()
        package['record']['model'] = 'changed'
        with self.assertRaises(ValueError):
            submissions.validate_submission(package, self.cohort)
        for key, value in [('id', 'wrong'), ('selection_sha256', '0' * 64), ('case_count', 61)]:
            package = self.package()
            package['cohort'][key] = value
            with self.subTest(key=key), self.assertRaises(ValueError):
                submissions.validate_submission(self.reseal(package), self.cohort)

    def test_bad_metrics_counters_nulls_and_self_review(self):
        invalid = [('linear', float('nan')), ('async', True), ('drs', 2), ('linear', None),
                   ('completedCases', True), ('scored', 281), ('episodes', 283), ('themeCount', 7),
                   ('observedLinear', .4), ('pairedComplete', 1), ('published', True),
                   ('reviewStatus', 'independently_reproduced'), ('executionStatus', 'running'),
                   ('rawScores', []), ('childPoolId', 'pool'), ('version', 'wrong')]
        for key, value in invalid:
            package = self.package()
            package['record'][key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                submissions.validate_submission(self.reseal(package), self.cohort)

    def test_unknown_envelope_and_invalid_commit(self):
        package = self.package()
        package['reviewStatus'] = 'materials_reviewed'
        with self.assertRaises(ValueError):
            submissions.validate_submission(self.reseal(package), self.cohort)
        with self.assertRaises(ValueError):
            submissions.package_run(self.root, self.root / 'manifest.json', benchmark_commit='../unsafe')

    def test_unreviewed_excluded_and_multiple_same_model(self):
        a, b = self.package(), self.package('c')
        self.save(a)
        self.save(b)
        self.assertEqual(submissions.load_accepted(self.root), [])
        self.review(a)
        self.review(b)
        accepted = submissions.load_accepted(self.root)
        self.assertEqual(len(accepted), 2)
        self.assertEqual(len({r['id'] for r in accepted}), 2)
        self.assertTrue(all(r['executionStatus'] == 'unknown' for r in accepted))
        self.assertTrue(all(r['published'] is True for r in accepted))

    def test_review_mismatch_and_reproduction_requires_evidence(self):
        package = self.package()
        self.save(package)
        for changes in [{'contentSha256': '0' * 64}, {'reviewStatus': 'independently_reproduced'},
                        {'evidenceUrl': 'file:///private'}, {'rawTrace': 'secret'}]:
            self.review(package, **changes)
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                submissions.load_accepted(self.root)
        self.review(package, reviewStatus='independently_reproduced', evidenceUrl='https://example.org/reproduction/123')
        self.assertEqual(submissions.load_accepted(self.root)[0]['reviewStatus'], 'independently_reproduced')

    def test_incomplete_reviewed_excluded(self):
        self.record.update({'completedCases': 0, 'scored': 0, 'pairedComplete': False, 'themeCount': 0,
                            'linear': None, 'async': None, 'drs': None, 'observedLinear': None,
                            'observedAsync': None, 'observedDrs': None, 'themeScores': {}})
        package = self.package()
        self.save(package)
        self.review(package)
        self.assertEqual(submissions.load_accepted(self.root), [])

    def test_duplicate_packages_rejected(self):
        package = self.package()
        path = self.save(package)
        shutil.copyfile(path, path.with_name('duplicate.json'))
        with self.assertRaises(ValueError):
            submissions.load_accepted(self.root)

    def test_theme_and_resource_validation(self):
        self.record['themeMetrics'] = {
            theme: {'linear': .5, 'async': .6, 'drs': .7, 'caseCount': count, 'completedCases': count}
            for theme, count in self.cohort['theme_counts'].items()}
        self.record['resources'] = {mode: {'tokens': {'mean': 1500, 'measuredEpisodes': 141},
                                          'durationMs': {'mean': None, 'measuredEpisodes': 0}}
                                    for mode in ['linear', 'async']}
        package = self.package()
        submissions.validate_submission(package, self.cohort)
        theme = next(iter(self.cohort['theme_counts']))
        mutations = [(['themeMetrics', theme, 'linear'], .9),
                     (['themeMetrics', theme, 'completedCases'], 0),
                     (['themeMetrics', theme, 'rawScore'], 1),
                     (['resources', 'linear', 'tokens', 'mean'], True),
                     (['resources', 'linear', 'tokens', 'measuredEpisodes'], 142),
                     (['resources', 'async', 'durationMs', 'mean'], 0)]
        for keys, value in mutations:
            modified = copy.deepcopy(package)
            target = modified['record']
            for key in keys[:-1]:
                target = target[key]
            target[keys[-1]] = value
            with self.subTest(keys=keys), self.assertRaises(ValueError):
                submissions.validate_submission(self.reseal(modified), self.cohort)

    def test_actual_package_cli_from_declared_manifest(self):
        cohort = self.cohort
        manifest = {key: cohort[key] for key in ['repetitions', 'seed', 'guidance',
                    'evaluation_contract_version', 'evaluation_contract_sha256']}
        manifest.update(model='new-participant-model', paper_eval_selection={
            'cohort': cohort['id'], 'selection_sha256': cohort['selection_sha256']})
        manifest['episodes'] = []
        for index, key in enumerate(cohort['instances']):
            case, instance = key.split('::')
            for mode in ['linear', 'async']:
                for repeat in range(3):
                    manifest['episodes'].append({'case_id': case, 'instance_id': instance,
                        'episode_id': f'episode-{index}-{mode}-{repeat}', 'execution_mode': mode,
                        'repeat': repeat, 'model': manifest['model'], 'guidance': cohort['guidance'],
                        'agent_seed': 2026, 'counterfactual_pair_id': f'pair-{index}-{repeat}'})
        path = self.root / 'declared-run/manifest.json'
        path.parent.mkdir()
        path.write_text(json.dumps(manifest), encoding='utf-8')
        result = subprocess.run([sys.executable, '-m', 'async_rbench.submissions', 'package',
            '--root', str(self.root), '--manifest', str(path), '--benchmark-commit', 'b' * 40],
            cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        identity = json.loads(result.stdout)['submissionId']
        package = json.loads((self.root / 'submissions/entries' / (identity + '.json')).read_text())
        submissions.validate_submission(package, cohort)
        self.assertEqual(package['record']['completedCases'], 0)
        self.assertIsNone(package['record']['linear'])
        self.assertEqual(package['record']['model'], 'new-participant-model')
        self.assertEqual(submissions.load_accepted(self.root), [])

    def test_duplicate_json_fields_rejected(self):
        path = self.save(self.package())
        path.write_text(path.read_text().replace('"schemaVersion": 1', '"schemaVersion": 1, "schemaVersion": 1'))
        with self.assertRaises(ValueError):
            submissions.load_accepted(self.root)

    def test_cli_roundtrip_and_review_immutable(self):
        package = self.package()
        path = self.save(package)
        def cli(*args):
            return subprocess.run([sys.executable, '-m', 'async_rbench.submissions', *args, '--root', str(self.root)],
                                  cwd=ROOT, capture_output=True, text=True)
        self.assertEqual(cli('validate', '--input', str(path)).returncode, 0)
        result = cli('review', '--input', str(path), '--status', 'materials_reviewed', '--reviewer', 'Maintainer')
        self.assertEqual(result.returncode, 0, result.stderr)
        result = cli('check')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)['accepted'], 1)
        self.assertNotEqual(cli('review', '--input', str(path), '--status', 'materials_reviewed', '--reviewer', 'Maintainer').returncode, 0)


if __name__ == '__main__':
    unittest.main()
