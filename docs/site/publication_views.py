"""Render public data into editorial templates, without private run access."""
from html import escape as esc
from collections import Counter
import json
import re

SOURCES = {'gaia2': 'GAIA2', 'multiagentbench': 'MultiAgentBench', 'osworld': 'OSWorld', 'swe-bench': 'SWE-bench', 'terminal-bench': 'Terminal-Bench'}
SCENARIOS = [
    ('delay', 'delayed_authoritative_result', 'Delayed authority', '权威结果延迟'),
    ('stale', 'late_or_out_of_order_superseded_result', 'Stale / out-of-order', '过时或乱序结果'),
    ('conflict', 'conflicting_valid_results', 'Conflicting results', '有效结果冲突'),
    ('replay', 'duplicate_or_replayed_completion', 'Duplicate / replayed', '重复或重放结果'),
    ('partial', 'partial_then_complete_result', 'Partial → complete', '部分到完整结果'),
    ('failure', 'child_failure_or_implicit_error', 'Subagent failure', '子代理失败'),
    ('scope', 'task_scope_or_dependency_change', 'Scope / dependencies', '范围或依赖变化'),
    ('straggler', 'straggler_under_resource_pressure', 'Resource stragglers', '资源压力下的慢任务'),
]
FULL_SCENARIOS = {
    'delay': ('Delayed authoritative result', '权威结果延迟'),
    'stale': ('Late or out-of-order superseded result', '已被替代的结果迟到或乱序到达'),
    'conflict': ('Conflicting valid-looking results', '表面有效的结果相互冲突'),
    'replay': ('Duplicate or replayed completion', '完成结果重复或重放'),
    'partial': ('Partial, then complete result', '部分结果后续补全'),
    'failure': ('Subagent failure or implicit error', '子代理失败或隐性错误'),
    'scope': ('Task scope or dependency change', '任务范围或依赖变化'),
    'straggler': ('Straggler under resource pressure', '资源压力下的慢任务'),
}

def bi(en, zh):
    return f'<span class="i18n" lang="en">{esc(en)}</span><span class="i18n" lang="zh">{esc(zh)}</span>'


def task_charts(corpus):
    """Count public task metadata; no source breakdown or private annotations."""
    tasks = corpus['tasks']
    difficulty = Counter(task['difficulty'] for task in tasks)
    total = len(tasks)
    medium_share = 100 * difficulty['medium'] / total if total else 0
    legend = ''.join(
        f'<div data-difficulty-count="{key}" data-count="{difficulty[key]}">'
        f'<dt><i class="difficulty-key {key}" aria-hidden="true"></i>{bi(en, zh)}</dt>'
        f'<dd>{difficulty[key]} <span>· {100 * difficulty[key] / total if total else 0:g}%</span></dd></div>'
        for key, en, zh in [('medium', 'Medium', '中等'), ('hard', 'Hard', '困难')])
    subtasks = Counter(task['subtasks'] for task in tasks)
    groups = [('2', '2', subtasks[2]), ('3', '3', subtasks[3]),
              ('4+', '≥4', sum(count for number, count in subtasks.items() if number >= 4))]
    peak = max((count for _, _, count in groups), default=0) or 1
    bars = ''.join(
        f'<li data-subtask-count="{key}" data-count="{count}" '
        f'style="--bar-height:{100 * count / peak:g}%">'
        f'<div class="subtask-column"><span class="subtask-value">{count}'
        f'<span class="sr-only"> {bi("task" if count == 1 else "tasks", "个任务")}</span></span>'
        '<span class="subtask-bar" aria-hidden="true"></span></div>'
        f'<span class="subtask-bin">{label}<span class="sr-only"> '
        f'{bi("initial subtasks per task", "个初始子任务／任务")}</span></span></li>'
        for key, label, count in groups)
    return (
        '<figure class="task-chart difficulty-chart"><figcaption>'
        + bi('Difficulty distribution', '难度分布') + '</figcaption>'
        '<div class="difficulty-body"><div class="difficulty-ring" '
        f'style="--medium-share:{medium_share:g}%" aria-hidden="true">'
        f'<div>{total}<span>{bi("tasks", "个任务")}</span></div></div>'
        f'<dl class="difficulty-legend">{legend}</dl></div></figure>'
        '<figure class="task-chart subtask-chart"><figcaption>'
        + bi('Initial subtasks per task', '每个任务的初始子任务数') + '</figcaption>'
        '<div class="subtask-axis" aria-hidden="true">' + bi('Tasks', '任务数') + '</div>'
        f'<ol class="subtask-bars">{bars}</ol></figure>')


def configure_participation(content, settings):
    """Opt-in rendering only; never activates a GitHub workflow or grants access."""
    guide = 'data-submission-guide' in content
    guide_link = ('' if guide else '<a class="text-link" href="/submission-guide/">'
                  + bi('Submission guide', '提交与审核说明') + ' →</a>')
    controls = ('<p class="submission-status">' + bi(
        'PR submissions are not open yet. The workflow is being tested locally.',
        'PR 提交尚未开放，工作流正在本地测试。') + '</p>' + guide_link)
    enabled = settings is not None and isinstance(settings, dict) and settings.get('enabled') is True
    if settings is None:
        return _participation_controls(content, controls, False)
    fields = {'enabled', 'template', 'app', 'community_url'}
    native = isinstance(settings, dict) and set(settings) == fields | {'workflow', 'maintainer'}
    if (not isinstance(settings, dict) or set(settings) not in (fields, fields | {'workflow', 'maintainer'})
            or type(settings['enabled']) is not bool
            or not re.fullmatch(r'[A-Za-z0-9-]+/[A-Za-z0-9_.-]+', str(settings['template']))
            or not re.fullmatch(r'[a-z0-9-]+', str(settings['app']))
            or not re.fullmatch(r'https://[A-Za-z0-9-]+\.github\.io/[A-Za-z0-9_.-]+/community\.json', str(settings['community_url']))
            or native and (settings['workflow'] != 'private-pr-v1'
                           or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9-]{0,38}', str(settings['maintainer'])))):
        raise ValueError('Invalid public PR configuration')
    if settings['enabled'] and not native:
        raise ValueError('PR intake is closed without explicit private-pr-v1 deployment configuration')
    content = re.sub(r'data-community-url="[^"]*"',
                     'data-community-url="' + esc(settings['community_url'], quote=True) + '"', content)
    if native:
        content = re.sub(r'(<span data-review-maintainer>).*?(</span>)',
                         lambda m: m[1] + '@' + esc(settings['maintainer']) + m[2], content)
    if enabled:
        controls = ('<div class="hero-links"><a class="button" href="https://github.com/'
                   + esc(settings['template']) + '/generate">' + bi(
                       'Create a private submission repository' if guide else 'Create private repository',
                       '创建私有提交仓库')
                   + '</a><a href="https://github.com/apps/' + esc(settings['app']) + '/installations/new">'
                   + bi('Install the review App', '安装审核 App') + ' ↗</a></div><p>'
                   + bi('Choose Private and invite @' + settings['maintainer'] + ' as a collaborator before opening your PR. Install the App on only this repository.',
                        '选择 Private，并在发起 PR 前邀请 @' + settings['maintainer'] + ' 为协作者。App 仅授权这个仓库。') + '</p>' + guide_link)
    return _participation_controls(content, controls, enabled)


def _participation_controls(content, controls, enabled):
    """Replace the whole controls area, including on previously built snapshots."""
    if 'data-submission-guide' in content:
        replacement = ('<!-- SUBMISSION_CONTROLS --><div id="submission-controls" data-submission-status="'
                       + ('open' if enabled else 'closed') + '">' + controls
                       + '</div><!-- /SUBMISSION_CONTROLS -->')
        content, count = re.subn(r'<!-- SUBMISSION_CONTROLS -->.*?<!-- /SUBMISSION_CONTROLS -->',
                                lambda _: replacement, content, count=1, flags=re.S)
        if count != 1:
            raise ValueError('Missing submission guide controls area')
        return content
    def replace(match):
        prefix = re.sub(r'data-submission-status="[^"]*"',
                        'data-submission-status="' + ('open' if enabled else 'closed') + '"', match[1])
        return prefix + '\n' + controls + match[2]
    content, count = re.subn(r'(<section id="participate"[^>]*>.*?</ol>).*?(</section>)',
                             replace, content, count=1, flags=re.S)
    if count != 1:
        raise ValueError('Missing participation controls area')
    return content

def render(content, source):
    paper = json.loads((source / 'data/leaderboard.json').read_text(encoding='utf-8'))
    corpus = json.loads((source / 'data/corpus.json').read_text(encoding='utf-8'))
    rows = []
    for rank, r in enumerate(paper['records'], 1):
        scores = ''.join(f'<td data-value="{r[k]:.1f}">{r[k]:.1f}</td>' for k in ('drs', 'async', 'batched', 'delta', 'calls'))
        scenarios = ''.join(f'<div><dt>{bi(en, zh)}</dt><dd>{r["scenarios"][key]["mean"]:.1f} <span>± {r["scenarios"][key]["sd"]:.1f}</span></dd></div>' for key, _, en, zh in SCENARIOS)
        rows.append(f'<tr data-paper-record="{esc(r["id"])}"><td>{rank:02}</td><th scope="row">{esc(r["model"])}</th>{scores}</tr><tr class="scenario-row"><td colspan="7"><dl>{scenarios}</dl></td></tr>')
    content = content.replace('<!-- PAPER_ROWS -->', '\n'.join(rows))
    content = content.replace('<!-- TASK_CHARTS -->', task_charts(corpus))
    content = content.replace('<!-- SCENARIO_COUNTS -->', ''.join(
        f'<div data-scenario-count="{short}" data-count="{corpus["scenario_counts"][key]}">'
        f'<dt>{bi(*FULL_SCENARIOS[short])}</dt><dd>{corpus["scenario_counts"][key]}</dd></div>'
        for short, key, _, _ in SCENARIOS))
    tasks = []
    for t in corpus['tasks']:
        tasks.append(f'<article class="task-entry" data-task="{esc(t["id"])}" data-source="{esc(t["source"])}" data-difficulty="{esc(t["difficulty"])}"><p class="task-meta">{esc(SOURCES[t["source"]])} · {bi("Medium" if t["difficulty"]=="medium" else "Hard", "中等" if t["difficulty"]=="medium" else "困难")} · {t["subtasks"]} {bi("initial subtasks", "初始子任务")}</p><h3><a href="{esc(t["url"], quote=True)}">{esc(t["title"])}</a></h3><code>{esc(t["id"])}</code></article>')
    content = content.replace('<!-- TASK_ROWS -->', '\n'.join(tasks))
    archive = json.loads((source / 'data/trajectories.public.json').read_text(encoding='utf-8'))
    content = content.replace('<!-- ARCHIVE_OPTIONS -->', ''.join(f'<option value="{esc(c["id"])}">{esc(c["title"]["en"])}</option>' for c in archive['cases']))
    group = lambda names: '<div class="margin-group">' + ''.join(f'<img src="/assets/context/{n}.svg" alt="" draggable="false">' for n in names) + '</div>'
    backdrop = '<div class="margin-motion" aria-hidden="true" inert>' + ''.join(f'<div class="margin-lane margin-{side}"><div class="margin-reel">{group(names) * 2}</div></div>' for side, names in [('left', ['profile', 'replay', 'revision']), ('right', ['artifacts', 'revision', 'replay'])]) + '</div>'
    return content.replace('<!-- MARGIN_BACKGROUND -->', backdrop)


def legacy_page(path):
    """Retire duplicate pages while retaining old public URLs."""
    if path in {'index.html', 'entry/index.html', 'benchmark/index.html', 'tasks/index.html', 'submission-guide/index.html'}:
        return None
    if path == 'evaluate/index.html':
        target = 'https://github.com/pope8zdt/Async-RBench#quick-start'
    elif path == 'overview/index.html':
        target = '/benchmark/#framework'
    elif path == 'leaderboard/index.html' or path.startswith('runs/'):
        target = '/benchmark/#leaderboard'
    else:
        target = '/tasks/#records'
    return f'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Async-RBench</title><script>document.documentElement.lang='en';try{{const p=JSON.parse(localStorage.getItem('async-rbench-paper-preferences')||'{{}}');document.documentElement.dataset.theme=p.theme==='dark'?'dark':'light'}}catch{{}}</script><link rel="stylesheet" href="/research.css"><script type="module" src="/legacy-page.mjs"></script></head><body><main><section class="chapter"><h1>Async-RBench</h1><p>This page has moved.</p><a data-destination href="{target}">Continue →</a></section></main></body></html>'''
