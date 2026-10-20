"""Synthetic records test the exporter; they are never shipped as showcase data."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest

SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))
from trajectories import export_case, validate_bundle


class TrajectoryExportTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / 'event_source.jsonl'
        self.records = [
            dict(seq=1, event_id='episode:1', episode_id='episode', elapsed_ms=10,
                 type='child_spawned', child_id='child-1', work_units=['patch']),
            dict(seq=2, event_id='episode:2', episode_id='episode', elapsed_ms=20,
                 type='result_delivered', completion_id='completion-1', child_id='child-1',
                 payload={'summary': 'private text', 'evidence': {'revision': 'abc'}}, api_key='NEVER_EXPORT'),
            dict(seq=3, event_id='episode:3', episode_id='episode', elapsed_ms=30,
                 type='result_presented', completion_id='completion-1', delivery_occurrence_id='occ-1'),
            dict(seq=4, event_id='episode:4', episode_id='episode', elapsed_ms=40,
                 type='verifier_result', hidden_tests=['NEVER_EXPORT']),
            dict(seq=5, event_id='episode:5', episode_id='episode', elapsed_ms=50,
                 type='main_action', kind='terminal', command='echo harmless'),
            dict(seq=6, event_id='episode:6', episode_id='episode', elapsed_ms=60,
                 type='episode_ended', local_status='incomplete', final_answer='NEVER_EXPORT'),
        ]
        self.spec = dict(id='test', title={'zh': '测试', 'en': 'Test'},
                         description={'zh': '说明', 'en': 'Description'},
                         model='test-model', episode_id='episode', source=str(self.source),
                         commands=[5], evidence={'2': ['revision']},
                         milestones=[dict(seq=3, title={'zh': '呈现', 'en': 'Presented'},
                                          note={'zh': '记录', 'en': 'Record'})])
        self.save()

    def save(self):
        self.source.write_text('\n'.join(json.dumps(e) for e in self.records), encoding='utf-8')
        self.spec['source_sha256'] = hashlib.sha256(self.source.read_bytes()).hexdigest()

    def test_allowlist_keeps_original_identity_and_excludes_private_data(self):
        case = export_case(self.spec)
        self.assertEqual([e['seq'] for e in case['events']], [1, 2, 3, 5, 6])
        self.assertEqual(case['events'][2]['event_id'], 'episode:3')
        self.assertEqual(case['events'][1]['record']['evidence'], {'revision': 'abc'})
        self.assertEqual(case['events'][3]['record']['command'], 'echo harmless')
        self.assertNotIn('NEVER_EXPORT', json.dumps(case))
        self.assertNotIn('private text', json.dumps(case))
        self.assertNotIn(str(self.source.parent), json.dumps(case))
        self.assertEqual(case['source_sha256'], self.spec['source_sha256'])

    def test_commands_require_explicit_review(self):
        self.spec['commands'] = []
        case = export_case(self.spec)
        self.assertNotIn('command', case['events'][3]['record'])

    def test_source_changes_and_unknown_milestones_are_rejected(self):
        self.spec['source_sha256'] = '0' * 64
        with self.assertRaises(ValueError):
            export_case(self.spec)
        self.save()
        self.spec['milestones'][0]['seq'] = 4  # Private event cannot become a public milestone.
        with self.assertRaises(ValueError):
            export_case(self.spec)

    def test_duplicate_identity_and_regressing_time_are_rejected(self):
        self.records[2]['event_id'] = 'episode:2'
        self.save()
        with self.assertRaises(ValueError):
            export_case(self.spec)
        self.records[2]['event_id'] = 'episode:3'
        self.records[2]['elapsed_ms'] = 0
        self.save()
        with self.assertRaises(ValueError):
            export_case(self.spec)

    def test_reviewed_secrets_fail_closed_instead_of_being_served(self):
        self.records[4]['command'] = 'export API_KEY=sk-123456789012345678901234'
        self.save()
        with self.assertRaises(ValueError):
            export_case(self.spec)

    def test_bundle_rejects_extra_fields_nonlocal_scope_and_duplicate_cases(self):
        case = export_case(self.spec)
        bundle = dict(version=1, local_only=True, cases=[case])
        validate_bundle(bundle)
        for bad in [dict(bundle, local_only=False), dict(bundle, cases=[case, case]), dict(bundle, judge={})]:
            with self.assertRaises(ValueError):
                validate_bundle(bad)
        bad = copy.deepcopy(bundle)
        bad['cases'][0]['events'][0]['record']['hidden_tests'] = ['secret']
        with self.assertRaises(ValueError):
            validate_bundle(bad)

    def test_local_builder_is_opt_in_and_refuses_project_publication_path(self):
        from build import build_site, ROOT
        bundle = dict(version=1, local_only=True, cases=[export_case(self.spec)])
        data = Path(self.tmp.name) / 'local.json'
        data.write_text(json.dumps(bundle), encoding='utf-8')
        output = Path(self.tmp.name) / 'local-site'
        build_site(ROOT, output, '', local_trajectories=data)
        page = (output / 'index.html').read_text(encoding='utf-8')
        self.assertIn('id="trajectory-player"', page)
        self.assertIn('id="example"', page)
        self.assertIn('Local preview', page)
        self.assertNotIn('data-example="illustrative"', page)
        self.assertTrue((output / 'data/trajectories.local.json').is_file())
        self.assertFalse((output / 'event_source.jsonl').exists())
        with self.assertRaises(ValueError):
            build_site(ROOT, Path(self.tmp.name) / 'refuse', '/Async-RBench', local_trajectories=data)

    def test_default_build_never_discovers_or_exports_local_logs(self):
        from build import build_site, ROOT
        output = Path(self.tmp.name) / 'default-site'
        build_site(ROOT, output, '')
        self.assertFalse((output / 'data/trajectories.local.json').exists())
        page = (output / 'index.html').read_text(encoding='utf-8')
        self.assertNotIn('id="trajectory-player"', page)


if __name__ == '__main__':
    unittest.main()
