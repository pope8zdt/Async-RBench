import importlib.util
import json
import re
import shutil
from pathlib import Path
import sys
import tempfile
import unittest
from html.parser import HTMLParser

SITE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SITE))
spec = importlib.util.spec_from_file_location('publication', SITE / 'publication.py')
publication = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publication)


class Elements(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.elements = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


class HomepageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory()
        cls.output = Path(cls.temp.name) / 'site'
        publication.build(SITE / 'published', cls.output, '/Async-RBench')
        cls.html = (cls.output / 'benchmark/index.html').read_text(encoding='utf-8')
        cls.nodes = Elements(cls.html).elements

    @classmethod
    def tearDownClass(cls):
        cls.temp.cleanup()

    def test_homepage_has_visible_explanations_not_disclosure_widgets(self):
        self.assertFalse(any(tag == 'details' for tag, _ in self.nodes))
        ids = {a.get('id') for _, a in self.nodes}
        self.assertTrue({'framework', 'framework-explanation', 'tasks', 'leaderboard', 'participate', 'citation'} <= ids)
        self.assertTrue({'guide', 'task-rows', 'trajectories'}.isdisjoint(ids))
        self.assertNotIn('research-facts', self.html)
        self.assertNotIn('/compact.mjs', self.html)

    def test_abstract_is_visible_between_intro_and_framework(self):
        section = re.search(r'<section id="abstract"[^>]*>(.*?)</section>', self.html, re.S)
        self.assertIsNotNone(section)
        self.assertLess(self.html.index('id="top"'), section.start())
        self.assertLess(section.end(), self.html.index('<section id="framework"'))
        nodes = Elements(section[0]).elements
        self.assertFalse(any(tag == 'details' or 'hidden' in attrs for tag, attrs in nodes))
        self.assertTrue(any(tag == 'p' and attrs.get('lang') == 'en'
                            and 'i18n' not in attrs.get('class', '').split()
                            for tag, attrs in nodes))

    def test_one_paper_table_contains_both_metrics_and_frozen_scenarios(self):
        rows = [a for tag, a in self.nodes if tag == 'tr' and 'data-paper-record' in a]
        paper = json.loads((SITE / 'published/data/leaderboard.json').read_text())
        self.assertEqual([r['data-paper-record'] for r in rows], [r['id'] for r in paper['records']])
        for record in paper['records']:
            row = re.search(r'<tr data-paper-record="' + re.escape(record['id']) + r'">(.*?)</tr><tr class="scenario-row">(.*?)</tr>', self.html)
            self.assertIsNotNone(row)
            self.assertEqual(re.findall(r'data-value="([^"]+)"', row[1]),
                             [f'{record[field]:.1f}' for field in ('drs', 'async', 'batched', 'delta', 'calls')])
            for key in ('delay', 'stale', 'conflict', 'replay', 'partial', 'failure', 'scope', 'straggler'):
                score = record['scenarios'][key]
                self.assertIn(f'<dd>{score["mean"]:.1f} <span>± {score["sd"]:.1f}</span></dd>', row[2])
        tabs = [a for _, a in self.nodes if a.get('role') == 'tab']
        self.assertEqual({a['aria-controls'] for a in tabs}, {'paper-panel', 'community-panel'})

    def test_task_browser_is_separate_and_preserves_all_public_cases(self):
        html = (self.output / 'tasks/index.html').read_text(encoding='utf-8')
        corpus = json.loads((SITE / 'published/data/corpus.json').read_text())
        self.assertEqual(len([a for tag, a in Elements(html).elements if 'data-task' in a]), len(corpus['tasks']))
        self.assertIn('/Async-RBench/data/trajectories.public.json', html)
        self.assertNotIn('story-rail.mjs', html)

    def test_task_charts_show_counts_from_the_public_corpus(self):
        section = re.search(r'<section id="tasks".*?</section>', self.html, re.S)[0]
        nodes = Elements(section).elements
        difficulty = {a['data-difficulty-count']: int(a['data-count'])
                      for _, a in nodes if 'data-difficulty-count' in a}
        subtasks = {a['data-subtask-count']: int(a['data-count'])
                    for _, a in nodes if 'data-subtask-count' in a}
        self.assertEqual(difficulty, {'medium': 104, 'hard': 96})
        self.assertEqual(subtasks, {'2': 73, '3': 40, '4+': 87})
        scenario_counts = [int(a['data-count']) for _, a in nodes
                           if 'data-scenario-count' in a]
        self.assertEqual(scenario_counts, [25] * 8)
        self.assertIn('href="/Async-RBench/tasks/"', section)
        self.assertNotIn('data-task=', self.html)
        viewer = (self.output / 'tasks/index.html').read_text(encoding='utf-8')
        self.assertIn('<title>Data viewer — Async-RBench</title>', viewer)

    def test_chart_geometry_changes_with_the_underlying_task_counts(self):
        # Catch a chart frozen to today's 104/96 split or counting subtasks
        # instead of tasks on the histogram's vertical axis.
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory)
            (source / 'data').mkdir()
            for name in ('leaderboard.json', 'trajectories.public.json'):
                shutil.copyfile(SITE / 'published/data' / name, source / 'data' / name)
            corpus = json.loads((SITE / 'published/data/corpus.json').read_text())
            corpus['tasks'] = corpus['tasks'][:4]
            for task, difficulty, subtasks in zip(
                    corpus['tasks'], ('medium', 'hard', 'hard', 'hard'), (2, 2, 4, 6)):
                task.update(difficulty=difficulty, subtasks=subtasks)
            (source / 'data/corpus.json').write_text(json.dumps(corpus), encoding='utf-8')
            html = publication._views.render('<!-- TASK_CHARTS -->', source)
            nodes = Elements(html).elements
            self.assertTrue(any(a.get('class') == 'difficulty-ring'
                                and '--medium-share:25%' in a.get('style', '')
                                for _, a in nodes))
            bars = {a['data-subtask-count']: a for _, a in nodes
                    if 'data-subtask-count' in a}
            self.assertEqual({key: int(a['data-count']) for key, a in bars.items()},
                             {'2': 2, '3': 0, '4+': 2})
            self.assertIn('--bar-height:100%', bars['2']['style'])
            self.assertIn('--bar-height:100%', bars['4+']['style'])
            self.assertIn('--bar-height:0%', bars['3']['style'])

    def test_guide_navigation_reaches_submission_review_and_sync_instructions(self):
        guide = (self.output / 'submission-guide/index.html').read_text(encoding='utf-8')
        nodes = Elements(guide).elements
        ids = {attrs.get('id') for _, attrs in nodes}
        links = {attrs.get('href') for tag, attrs in nodes if tag == 'a'}
        for target in ('participant-steps', 'reviewer-steps', 'sync-status'):
            self.assertIn(target, ids)
            self.assertIn('#' + target, links)
        self.assertIn('/Async-RBench/benchmark/#community-panel', links)
        self.assertIn(
            'https://github.com/pope8zdt/Async-RBench-reviews/actions/workflows/private-review.yml',
            links)

    def test_citation_is_inline_and_copyable(self):
        self.assertIn('@misc{async_rbench', self.html)
        self.assertTrue(any(a.get('data-copy-target') == 'bibtex' for _, a in self.nodes))
        self.assertFalse(any('download' in a and 'CITATION' in a.get('href', '') for _, a in self.nodes))

    def test_submission_stays_closed_and_has_no_public_posting_form(self):
        self.assertNotIn('issues/new', self.html)
        self.assertNotIn('data-github-submission-root', self.html)
        self.assertIn('data-submission-status="closed"', self.html)

    def test_closed_submission_has_a_local_read_only_guide(self):
        section = re.search(r'<section id="participate".*?</section>', self.html, re.S)[0]
        links = [a.get('href') for tag, a in Elements(section).elements if tag == 'a']
        self.assertIn('/Async-RBench/submission-guide/', links)
        guide = (self.output / 'submission-guide/index.html').read_text(encoding='utf-8')
        nodes = Elements(guide).elements
        self.assertTrue(any(a.get('id') == 'participant-steps' for _, a in nodes))
        self.assertTrue(any(a.get('id') == 'reviewer-steps' for _, a in nodes))
        self.assertFalse(any(tag in {'form', 'input'} for tag, _ in nodes))
        self.assertFalse(any('/generate' in a.get('href', '') or '/installations/new' in a.get('href', '')
                             for _, a in nodes))
        self.assertNotIn('data-destination', guide)  # must not be rewritten as a legacy redirect
        self.assertIn('/Async-RBench/benchmark/#participate', guide)

    def test_old_pages_point_to_canonical_content(self):
        old = (self.output / 'trajectories/index.html').read_text(encoding='utf-8')
        self.assertIn('/Async-RBench/tasks/#records', old)
        guide = (self.output / 'evaluate/index.html').read_text(encoding='utf-8')
        self.assertIn('https://github.com/pope8zdt/Async-RBench#quick-start', guide)
        self.assertNotIn('id="guide"', guide)

    def test_old_enable_flag_cannot_enable_unimplemented_pr_intake(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {'enabled': True, 'template': 'owner/template', 'app': 'review-app', 'community_url': 'https://owner.github.io/community/community.json'}
            with self.assertRaisesRegex(ValueError, 'intake is closed'):
                publication.build(SITE / 'published', Path(directory) / 'out', '', 'github-private', config)

    def test_explicit_pr_deployment_config_renders_private_entry_and_preserves_paper(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {'enabled': True, 'template': 'owner/template', 'app': 'review-app',
                      'community_url': 'https://owner.github.io/community/community.json',
                      'workflow': 'private-pr-v1', 'maintainer': 'review-owner'}
            output = Path(directory) / 'out'
            publication.build(SITE / 'published', output, '/Async-RBench', 'github-private', config)
            html = (output/'benchmark/index.html').read_text(encoding='utf-8')
            self.assertIn('data-submission-status="open"', html)
            section = re.search(r'<section id="participate".*?</section>', html, re.S)[0]
            actions = [attrs for tag, attrs in Elements(section).elements
                       if tag == 'a' and 'button' in attrs.get('class', '').split()]
            self.assertEqual([a['href'] for a in actions], ['/Async-RBench/submission-guide/'])
            # The public entry must lead to the instructions, not grant access
            # or create a repository before the participant knows what to submit.
            self.assertNotIn('/generate', section)
            self.assertNotIn('/installations/new', section)
            self.assertNotIn('issues/new', html)
            self.assertEqual((output/'data/leaderboard.json').read_bytes(),
                             (SITE/'published/data/leaderboard.json').read_bytes())

    def test_guide_uses_the_same_open_entry_and_maintainer(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {'enabled': True, 'template': 'owner/template', 'app': 'review-app',
                      'community_url': 'https://owner.github.io/community/community.json',
                      'workflow': 'private-pr-v1', 'maintainer': 'review-owner'}
            output = Path(directory) / 'out'
            publication.build(SITE / 'published', output, '/Async-RBench', 'github-private', config)
            guide = (output/'submission-guide/index.html').read_text(encoding='utf-8')
            self.assertIn('data-submission-status="open"', guide)
            create_step = re.search(r'<li id="create-repository".*?</li>', guide, re.S)
            access_step = re.search(r'<li id="review-access".*?</li>', guide, re.S)
            self.assertIsNotNone(create_step)
            self.assertIsNotNone(access_step)
            self.assertIn('https://github.com/owner/template/generate', create_step[0])
            self.assertIn('https://github.com/apps/review-app/installations/new', access_step[0])
            self.assertIn('@review-owner', access_step[0])
            header = re.search(r'<section class="chapter browser-heading".*?</section>', guide, re.S)[0]
            self.assertNotIn('/generate', header)
            self.assertNotIn('/installations/new', header)
            self.assertIn('@review-owner', guide)
            self.assertNotIn('@pope8zdt', guide)
            self.assertNotIn('submissions are not open', guide)
            self.assertNotIn('尚未开放', guide)

    def test_shipped_release_opens_both_entries_without_changing_paper_data(self):
        settings = json.loads((SITE/'participation.json').read_text(encoding='utf-8'))
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / 'out'
            publication.build(SITE/'published', output, '/Async-RBench', 'github-private', settings)
            for page in ('benchmark/index.html', 'submission-guide/index.html'):
                html = (output/page).read_text(encoding='utf-8')
                self.assertIn('data-submission-status="open"', html)
                self.assertNotIn('issues/new', html)
            guide = (output/'submission-guide/index.html').read_text(encoding='utf-8')
            self.assertIn('https://github.com/pope8zdt/Async-RBench-submission-template/generate', guide)
            self.assertIn('https://github.com/apps/async-rbench-review-pope8zdt/installations/new', guide)
            self.assertEqual(
                json.loads((output/'data/community.json').read_text(encoding='utf-8'))['entries'], [])
            self.assertEqual((output/'data/leaderboard.json').read_bytes(),
                             (SITE/'published/data/leaderboard.json').read_bytes())

    def test_entry_rejects_invalid_maintainer_and_destination(self):
        config = {'enabled': True, 'template': 'owner/template', 'app': 'review-app',
                  'community_url': 'https://owner.github.io/community/community.json',
                  'workflow': 'private-pr-v1', 'maintainer': 'review-owner'}
        for field, value in [('maintainer', 'owner"><script>'),
                             ('community_url', 'https://example.org/community.json'),
                             ('template', 'https://example.org'),
                             ('workflow', 'unrecognized')]:
            with self.subTest(field=field), tempfile.TemporaryDirectory() as directory:
                with self.assertRaisesRegex(ValueError, 'Invalid public PR configuration'):
                    publication.build(SITE/'published', Path(directory)/'out', '',
                                      'github-private', dict(config, **{field: value}))

    def test_rebuilding_enabled_site_can_close_intake(self):
        with tempfile.TemporaryDirectory() as directory:
            config = {'enabled': True, 'template': 'owner/template', 'app': 'review-app',
                      'community_url': 'https://owner.github.io/community/community.json',
                      'workflow': 'private-pr-v1', 'maintainer': 'review-owner'}
            enabled = Path(directory) / 'enabled'
            publication.build(SITE / 'published', enabled, '', 'github-private', config)
            for name, mode, settings in [('disabled', 'github-private', dict(config, enabled=False)),
                                          ('default', 'legacy', None)]:
                output = Path(directory) / name
                publication.build(enabled, output, '', mode, settings)
                html = (output/'benchmark/index.html').read_text(encoding='utf-8')
                self.assertIn('data-submission-status="closed"', html)
                self.assertNotIn('/generate', html)
                self.assertNotIn('/installations/new', html)
                self.assertIn('PR submissions are not open yet', html)
                guide = (output/'submission-guide/index.html').read_text(encoding='utf-8')
                self.assertIn('data-submission-status="closed"', guide)
                self.assertNotIn('/generate', guide)
                self.assertNotIn('/installations/new', guide)
                self.assertIn('PR submissions are not open yet', guide)


if __name__ == '__main__':
    unittest.main()
