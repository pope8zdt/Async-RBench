"""Exercise the public merge boundary without building the site or running models."""
import copy
import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'website/scripts'))

from async_rbench.main_experiment import load_main_cohort
from async_rbench.main_results import aggregate_model
from async_rbench import submissions
import prepare_data


class PrepareDataTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for directory in ['experiments/formal-47', 'experiments/formal-61']:
            shutil.copytree(ROOT / directory, self.root / directory)
        shutil.copyfile(ROOT / 'evaluation_contract.json', self.root / 'evaluation_contract.json')
        self.cohort = load_main_cohort(self.root)
        self.target = self.root / 'website/public/data'
        self.target.mkdir(parents=True)
        self.snapshot = {
            'generatedAt': '2026-09-06T12:00:00+00:00',
            'source': 'Main-47 manifest-bound episode scores. Historical splits do not filter this cohort.',
            'cohort': {key: self.cohort[key] for key in submissions.COHORT_FIELDS | {'models'}},
            'records': [self.record(model) for model in self.cohort['models']],
        }
        # Corpus generation has separate real-registry tests; keep this suite focused on merging.
        self.addCleanup(patch.stopall)
        patch.object(prepare_data, 'build_catalog', return_value={
            'generatedAt': '2026-09-06T13:00:00+00:00', 'caseCount': 200, 'instanceCount': 201,
        }).start()

    def record(self, model, complete=False):
        scores = {}
        if complete:
            scores = {(key, mode, repeat): {'score_status': 'scored', 'base_task_score': .5, 'async_drs': .6}
                      for key in self.cohort['instances'] for mode in ['linear', 'async'] for repeat in range(3)}
        return {**aggregate_model(model, self.cohort, scores), 'sourceSha256': 'a' * 64, 'date': None}

    def write_snapshot(self, snapshot=None):
        (self.target / 'experiments.json').write_text(json.dumps(snapshot or self.snapshot), encoding='utf-8')

    def assert_rejected(self, snapshot):
        self.write_snapshot(snapshot)
        with self.assertRaises(ValueError):
            prepare_data.prepare(self.root)
        self.assertFalse((self.target / 'leaderboard.json').exists())
        self.assertFalse((self.target / 'corpus.json').exists())

    def test_wrong_snapshot_cohort_metadata_rejected_even_with_correct_selection_digest(self):
        changes = [('id', 'not-main-47'), ('repetitions', 1), ('case_count', 61),
                   ('models', ['different-model']), ('theme_counts', {})]
        for key, value in changes:
            snapshot = copy.deepcopy(self.snapshot)
            snapshot['cohort'][key] = value
            with self.subTest(key=key):
                self.assert_rejected(snapshot)

    def test_unknown_fields_never_reach_public_output(self):
        for location in ['snapshot', 'cohort', 'record', 'theme', 'resource']:
            snapshot = copy.deepcopy(self.snapshot)
            record = snapshot['records'][0]
            target = {'snapshot': snapshot, 'cohort': snapshot['cohort'], 'record': record,
                      'theme': next(iter(record['themeMetrics'].values())),
                      'resource': record['resources']['linear']['tokens']}[location]
            target['privateTrace'] = 'DO NOT PUBLISH'
            with self.subTest(location=location):
                self.assert_rejected(snapshot)

    def test_malformed_snapshot_metrics_counters_and_statuses_rejected(self):
        changes = [('caseCount', 61), ('completedCases', True), ('episodes', 1), ('scored', -1),
                   ('linear', .9), ('observedDrs', .6), ('version', 'wrong'),
                   ('scope', 'track_b'), ('pairedComplete', True), ('published', True),
                   ('reviewStatus', 'independently_reproduced'), ('executionStatus', 'running'),
                   ('coverageStatus', 'complete'), ('date', 'not-a-date')]
        for key, value in changes:
            snapshot = copy.deepcopy(self.snapshot)
            snapshot['records'][0][key] = value
            with self.subTest(key=key):
                self.assert_rejected(snapshot)

    def test_snapshot_cannot_omit_or_duplicate_a_panel_model(self):
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['records'].pop()
        self.assert_rejected(snapshot)
        snapshot = copy.deepcopy(self.snapshot)
        snapshot['records'][1] = copy.deepcopy(snapshot['records'][0])
        snapshot['records'][1]['id'] = 'b' * 16
        self.assert_rejected(snapshot)

    def test_invalid_snapshot_metadata_and_duplicate_json_keys_rejected(self):
        for key, value in [('generatedAt', 'not-a-date'), ('source', {'private': 'secret'}), ('records', {})]:
            snapshot = copy.deepcopy(self.snapshot)
            snapshot[key] = value
            with self.subTest(key=key):
                self.assert_rejected(snapshot)
        self.write_snapshot()
        path = self.target / 'experiments.json'
        path.write_text(path.read_text().replace('"case_count": 47', '"case_count": 61, "case_count": 47'))
        with self.assertRaises(ValueError):
            prepare_data.prepare(self.root)

    def test_legacy_snapshot_remains_incomplete_self_reported_with_unknown_execution(self):
        for record in self.snapshot['records']:
            for key in ['coverageStatus', 'reviewStatus', 'executionStatus', 'resources', 'themeMetrics']:
                record.pop(key)
        self.write_snapshot()
        prepare_data.prepare(self.root)
        result = json.loads((self.target / 'leaderboard.json').read_text())
        self.assertEqual(len(result['records']), len(self.cohort['models']))
        for record in result['records']:
            self.assertEqual(record['coverageStatus'], 'incomplete')
            self.assertEqual(record['reviewStatus'], 'self_reported')
            self.assertEqual(record['executionStatus'], 'unknown')
            self.assertIsNone(record['drs'])

    def test_reviewed_complete_same_model_runs_merge_as_distinct_records(self):
        for source in ['b', 'c']:
            record = self.record('participant-model', complete=True)
            record.pop('id')
            record['sourceSha256'] = source * 64
            package = {'schemaVersion': 1,
                       'cohort': {key: self.cohort[key] for key in submissions.COHORT_FIELDS},
                       'benchmarkCommit': 'd' * 40, 'configSha256': None, 'record': record}
            package['submissionId'] = package['contentSha256'] = submissions._identity(package)
            identity = package['submissionId']
            review = {'schemaVersion': 1, 'submissionId': identity, 'contentSha256': identity,
                      'reviewStatus': 'materials_reviewed', 'reviewer': 'Maintainer',
                      'reviewedAt': '2026-09-06T12:00:00+00:00', 'evidenceUrl': None}
            for directory, value in [('entries', package), ('reviews', review)]:
                path = self.root / 'submissions' / directory / (identity + '.json')
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(json.dumps(value), encoding='utf-8')
        self.write_snapshot()
        prepare_data.prepare(self.root)
        records = json.loads((self.target / 'leaderboard.json').read_text())['records']
        accepted = [record for record in records if record['model'] == 'participant-model']
        self.assertEqual(len(accepted), 2)
        self.assertEqual(len({record['id'] for record in records}), len(records))
        self.assertTrue(all(record['published'] and record['pairedComplete'] for record in accepted))
        self.assertTrue(all(record['reviewStatus'] == 'materials_reviewed' for record in accepted))
        self.assertTrue(all(record['executionStatus'] == 'unknown' for record in records))


if __name__ == '__main__':
    unittest.main()
