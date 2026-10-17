import importlib.util
import json
from pathlib import Path
import tempfile
import unittest

SITE = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('publication', SITE / 'publication.py')
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


class PublicationTests(unittest.TestCase):
    def test_project_prefix_is_idempotent(self):
        text = '<a href="/benchmark/#guide">Run</a><a href="#guide">Jump</a><a href="https://github.com/x">Source</a><img src="/assets/a.svg">'
        result = publication.prefix_paths(text, '/Async-RBench')
        self.assertIn('href="/Async-RBench/benchmark/#guide"', result)
        self.assertIn('src="/Async-RBench/assets/a.svg"', result)
        self.assertIn('href="#guide"', result)
        self.assertIn('href="https://github.com/x"', result)
        self.assertEqual(result, publication.prefix_paths(result, '/Async-RBench'))

    def test_javascript_templates_and_entry_redirect_use_project_root(self):
        text = "const src=`/assets/scene-${id}.png`; if(url.pathname !== '/' && url.pathname !== '/index.html') return null;"
        result = publication.prefix_paths(text, '/Async-RBench')
        self.assertIn('`/Async-RBench/assets/scene-${id}.png`', result)
        self.assertIn("url.pathname !== '/Async-RBench/'", result)
        self.assertIn("url.pathname !== '/Async-RBench/index.html'", result)
        self.assertEqual(publication.prefix_paths('cd /app/repo; /bin/sh', '/Async-RBench'), 'cd /app/repo; /bin/sh')

    def test_archive_is_an_explicit_selection(self):
        source = {'id': 'continue', 'milestones': [{'seq': 387}], 'source_name': 'C:/private/trace.jsonl',
                  'events': [{'seq': 387, 'type': 'child_cancelled', 'record': {'child_id': 'child-1'}},
                             {'seq': 100, 'type': 'model_reply', 'record': {'reasoning': 'private'}}]}
        result = publication.public_archive({'local_only': True, 'cases': [source]})
        self.assertEqual(result['publication'], 'reviewed-excerpts-v1')
        self.assertEqual([e['seq'] for e in result['cases'][0]['events']], [387])
        self.assertNotIn('local_only', result)
        self.assertNotIn('source_name', result['cases'][0])
        self.assertNotIn('reasoning', json.dumps(result))

    def test_publication_rejects_credentials_and_local_machine_paths(self):
        for text in ['Bearer sk-' + 'x'*40, 'ghp_' + 'x'*36, 'C:\\Users\\pope\\secret.json']:
            with self.subTest(text=text[:8]), self.assertRaises(ValueError):
                publication.assert_public_text(text, 'fixture')

    def test_broken_reference_is_a_release_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root/'index.html').write_text('<img src="/Async-RBench/assets/missing.png">', encoding='utf-8')
            with self.assertRaises(ValueError):
                publication.validate_site(root, '/Async-RBench')

    def test_root_relative_snapshot_is_complete_and_paper_assets_unchanged(self):
        publication.validate_snapshot(SITE/'published')

    def test_deployment_build_has_no_local_data_and_all_links_resolve(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)/'site'
            result = publication.build(SITE/'published', output, '/Async-RBench')
            self.assertEqual(result['pages'], 22)
            self.assertFalse(list(output.rglob('*.local.json')))
            self.assertFalse((output/'docs').exists())
            page = (output/'benchmark/index.html').read_text(encoding='utf-8')
            self.assertIn('/Async-RBench/data/trajectories.public.json', page)
            self.assertNotIn('Local preview', page)
            self.assertNotIn('Put your agent to the test.', page)
            self.assertIn('Run an evaluation', page)
            self.assertIn('data-github-submission-root', page)
            self.assertIn('data-static-mode="true"', page)
            self.assertIn('data-community-url="/Async-RBench/data/community.json"', page)
            self.assertIn('href="#participate"', page)
            for name in ('github-app.mjs', 'github-static.mjs', 'github-style.css'):
                self.assertTrue((output/'assets/submissions'/name).is_file())
            board = json.loads((output/'data/community.json').read_text(encoding='utf-8'))
            self.assertEqual(board, {'schema': 'async-rbench-community-board-1', 'entries': []})

    def test_build_never_overwrites_existing_content(self):
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory)
            (output/'keep.txt').write_text('keep', encoding='utf-8')
            with self.assertRaises(ValueError):
                publication.build(SITE/'published', output, '')
            self.assertEqual((output/'keep.txt').read_text(encoding='utf-8'), 'keep')


if __name__ == '__main__':
    unittest.main()
