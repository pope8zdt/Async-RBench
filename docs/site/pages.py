"""Readable HTML is the default; JavaScript only enhances controls."""
from html import escape
import json

REPO = "https://github.com/pope8zdt/Async-RBench"
SOURCES = {"gaia2": "GAIA2", "multiagentbench": "MultiAgentBench", "osworld": "OSWorld", "swe-bench": "SWE-bench", "terminal-bench": "Terminal-Bench"}
MODEL_ICONS = {
    "claude-sonnet-5": "claude-color.svg", "gpt-5.6-terra": "openai.svg",
    "qwen3.7-plus": "qwen-color.svg", "glm-5.3-flash": "zai.svg",
    "gpt-5.6-luna": "openai.svg", "deepseek-v4-pro": "deepseek-color.svg",
    "qwen3.5-27b": "qwen-color.svg", "kimi-k2.5": "kimi-color.svg",
    "gemini-3-flash-preview-thinking-high": "gemini-color.svg",
}
SCENARIOS = [
    ("delay", "权威结果延迟", "Delayed authority", "采纳迟到的权威证据，修正受影响的工作。", "Adopt authoritative evidence and revise affected work."),
    ("stale", "过时与乱序结果", "Staleness and ordering", "识别过时结果，保留当前有效状态。", "Reject stale results and preserve the current valid state."),
    ("conflict", "有效结果冲突", "Conflicting results", "依据证据而非到达顺序解决分歧。", "Resolve conflicts by evidence, not arrival order."),
    ("replay", "重复与重放", "Duplication and replay", "保持幂等，避免重复操作和不必要的重建。", "Remain idempotent; avoid repeated side effects and needless rebuilding."),
    ("partial", "部分到完整结果", "Partial to complete", "区分临时证据与完整结果，验证整合后的状态。", "Distinguish provisional from complete evidence and verify integration."),
    ("failure", "子代理失败", "Subagent failure", "恢复失败的子任务，同时保留其他有效进展。", "Recover the failed subtask while preserving valid progress elsewhere."),
    ("scope", "范围与依赖变化", "Scope and dependencies", "调整任务范围和依赖，并重新检查受影响的工作。", "Revise scope and dependencies, then recheck affected work."),
    ("straggler", "资源压力下的慢任务", "Resource stragglers", "权衡等待、取消与调度，保护已完成的工作。", "Balance waiting, cancellation and scheduling while protecting completed work."),
]


def t(zh, en):
    return f'<span class="i18n" lang="zh">{escape(zh)}</span><span class="i18n" lang="en">{escape(en)}</span>'


def code(text):
    return f'<pre tabindex="0"><code>{escape(text)}</code></pre>'


def document(base, route, title, body):
    nav = [("", "概览", "Overview"), ("leaderboard/", "榜单", "Leaderboard"), ("tasks/", "任务", "Tasks"), ("evaluate/", "使用指南", "Guide"), ("docs/", "协议", "Protocol")]
    links = ''.join(f'<a href="{base}/{path}" {"aria-current=page" if route == path else ""}>{t(zh,en)}</a>' for path, zh, en in nav)
    return f'''<!doctype html>
<html lang="zh" data-theme="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Async-RBench: 200 tasks for asynchronous task execution in LLM agents. Paper results, public tasks and evaluation protocol.">
<meta name="color-scheme" content="light dark"><title>{escape(title)} · Async-RBench</title>
<link rel="stylesheet" href="{base}/assets/site.css">
<script>try{{const p=JSON.parse(localStorage.getItem('async-rbench-paper-preferences')||'{{}}');document.documentElement.lang=p.language==='en'?'en':'zh';document.documentElement.dataset.theme=p.theme==='dark'||(!p.theme&&matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light'}}catch{{}}</script>
<script type="module" src="{base}/assets/site.mjs"></script></head>
<body data-base="{base}" class="{'leaderboard-page' if route == 'leaderboard/' else 'home-page' if route == '' else ''}"><a class="skip-link" href="#main">{t('跳转到内容','Skip to content')}</a>
<header class="site-header"><div class="header-inner"><a class="brand" href="{base}/">Async-RBench</a>
<nav aria-label="Main navigation">{links}</nav><div class="preferences" hidden data-enhance>
<button id="language" type="button">English</button><button id="theme" type="button">{t('深色','Dark')}</button></div></div></header>
<main id="main" tabindex="-1">{body}</main>
<footer><a class="brand" href="{base}/">Async-RBench</a><span>{t('200 个任务 · v11.0-paper','200 tasks · v11.0-paper')}</span>
<a href="{REPO}">GitHub</a><a href="{base}/docs/#sources">{t('数据与说明','Sources & scope')}</a></footer>
<noscript><p class="noscript">页面内容无需 JavaScript 即可阅读。筛选、切换语言与主题需要启用 JavaScript。 / All content is readable without JavaScript. Enable it for filters, language and theme controls.</p></noscript>
</body></html>'''


def figure(base, name, zh, en):
    if name.endswith('.svg'):
        return f'<figure class="scientific-figure"><div class="diagram-scroll" tabindex="0" role="region" aria-label="{escape(en)}"><img src="{base}/assets/{name}" alt="{escape(en)}" loading="lazy"></div><figcaption>{t(zh,en)} <a href="{base}/assets/{name}" download>SVG ↓</a></figcaption></figure>'
    return f'<figure><a href="{base}/assets/{name}" aria-label="{escape(en)}"><img src="{base}/assets/{name}" alt="{escape(en)}" loading="lazy"></a><figcaption>{t(zh,en)}</figcaption></figure>'


def heading(label, zh, en, lead_zh, lead_en, icon=''):
    title = f'<span class="model-link">{icon}<span>{t(zh,en)}</span></span>' if icon else t(zh,en)
    return f'<section class="page-heading"><h1>{title}</h1><p class="lead">{t(lead_zh,lead_en)}</p></section>'


def model_icon(base, record):
    name = MODEL_ICONS[record['id']]
    dark = ' model-icon-dark' if name == 'kimi-color.svg' else ''
    return f'<img class="model-icon{dark}" src="{base}/assets/model-icons/{name}" width="32" height="32" alt="" aria-hidden="true">'


def model_link(base, record):
    label = escape(record.get('paper_label', record['model']))
    return f'<a class="model-link" href="{base}/runs/{record["id"]}/">{model_icon(base,record)}<span>{label}</span></a>'


def source_note(base, table=None):
    zh = f'来源：第 26 版论文（2026-09-29），表 {table}。' if table else '来源：第 26 版论文（2026-09-29），表 3、表 4。'
    en = f'Source: manuscript v26 (2026-09-29), Table {table}.' if table else 'Source: manuscript v26 (2026-09-29), Tables 3 and 4.'
    return f'<p class="source-note">{t(zh,en)} <a href="{base}/docs/#sources">{t("数据说明", "Data notes")}</a></p>'


def score_bar(value, label):
    return f'<span class="score"><meter min="0" max="100" value="{value:.1f}" aria-label="{escape(label)}" aria-valuetext="{value:.1f} / 100">{value:.1f} / 100</meter><span class="score-value" aria-hidden="true">{value:.1f}</span></span>'


SCENARIO_LABELS = dict(zip(
    [s[0] for s in SCENARIOS],
    ["Delay", "Stale", "Conflict", "Replay", "Partial", "Failure", "Scope", "Strag."],
    strict=True,
))


def scenario_scores(scenarios, maxima=None, detailed=False):
    items = []
    for key, zh, en, *_ in SCENARIOS:
        result = scenarios[key]
        mean = result["mean"] if isinstance(result, dict) else result
        sd = f' <small class="uncertainty">±{result["sd"]:.1f}</small>' if isinstance(result, dict) else ''
        tag = 'strong' if maxima and mean == maxima[key] else 'span'
        label = t(zh, en) if detailed else f'<abbr title="{escape(en)}">{SCENARIO_LABELS[key]}</abbr>'
        items.append(f'<div><dt>{label}</dt><dd data-field="{key}"><{tag}>{mean:.1f}</{tag}>{sd}</dd></div>')
    return f'<dl class="scenario-scores {"scenario-detail" if detailed else ""}">{"".join(items)}</dl>'


def call_count(calls):
    return f'<dl class="call-count"><dt>Calls</dt><dd data-field="calls">{calls:.1f}</dd></dl>'


def result_rows(base, paper, limit=None):
    maxima = {key: max(r["scenarios"][key]["mean"] for r in paper["records"]) for key in paper["scenario_order"]}
    rows = []
    for rank, record in enumerate(sorted(paper["records"], key=lambda r: -r["drs"])[:limit], 1):
        rows.append(f'''<li class="rank-card" data-record="{record['id']}" data-place="{rank}" value="{rank}"><article>
<div class="rank-card-heading"><span class="rank-number" aria-hidden="true">{rank:02d}</span><div class="rank-identity"><h3>{model_link(base,record)}</h3>{call_count(record['calls'])}</div>
<div class="rank-score"><span class="score-label">DRS <small>/ 100</small></span>{score_bar(record['drs'], record['model'] + ' DRS')}</div></div>
{scenario_scores(record['scenarios'], maxima)}</article></li>''')
    return ''.join(rows)


def leaderboard(base, paper, compact=False):
    if compact:
        return f'''<p class="ranking-caption">{t('DRS 前三名 · 八场景均值 ± 标准差；粗体为九模型中的场景最高分。','Top three by DRS · eight scenario means ± sample SD; bold marks the best among all nine agents.')}</p>
<ol id="result-rows" class="rank-list" role="list" aria-label="DRS leaderboard">{result_rows(base,paper,limit=3)}</ol>
<p id="result-empty" class="empty-state" hidden></p>{source_note(base,3)}'''
    scenario_options = ''.join(f'<option value="{key}">{SCENARIO_LABELS[key]} ↓</option>' for key in paper["scenario_order"])
    controls = '' if compact else f"""<div class="filters result-filters" data-enhance hidden><label>{t('搜索模型','Search agents')}<input id="model-search" type="search" autocomplete="off" aria-controls="result-rows success-rows"></label>
<label>{t('排名依据','Rank by')}<select id="metric" aria-controls="result-rows"><option value="drs">DRS ↓</option>{scenario_options}</select></label>
<div class="result-downloads"><a href="{base}/data/leaderboard.json" download>JSON</a><a href="{base}/data/leaderboard.csv" download>CSV</a></div></div>"""
    mean = paper['mean']
    return f"""{controls}<p class="ranking-caption">{t('八场景均值 ± 标准差；粗体为各场景最高分。','Eight scenario means ± sample SD; best scores in bold.')}</p>
<ol id="result-rows" class="rank-list" role="list" aria-label="DRS leaderboard">{result_rows(base,paper)}</ol>
<p id="result-empty" class="empty-state" role="status" hidden>{t('没有匹配的模型。请尝试其他关键词。','No matching agents. Try another search.')}</p>
<aside class="ranking-mean drs-mean" data-summary="drs-mean"><div class="rank-card-heading"><div class="rank-identity"><h3>{t('九模型均值','Nine-agent mean')}</h3>{call_count(mean['calls'])}</div><div class="rank-score"><span class="score-label">DRS <small>/ 100</small></span>{score_bar(mean['drs'], 'Mean DRS')}</div></div>{scenario_scores(mean['scenarios'])}</aside>
<p class="result-note">{t('Calls：每次 Async 运行中主代理与全部子代理的平均响应总数。','Calls: mean total main-agent and subagent responses per Async run.')} <a href="{base}/docs/#scoring">{t('计分方法','Scoring protocol')} →</a></p>{source_note(base,3) if compact else ''}"""


def success_leaderboard(base, paper):
    rows = []
    maxima = {key: max(r[key] for r in paper["records"]) for key in ("batched", "async")}
    for rank, record in enumerate(sorted(paper["records"], key=lambda r: -r["drs"]), 1):
        rates = ''.join(f'<div><dt>{label} S <small>(%)</small></dt><dd data-field="{key}"><{"strong" if record[key] == maxima[key] else "span"}>{record[key]:.1f}</{"strong" if record[key] == maxima[key] else "span"}></dd></div>' for key, label in (("batched", "Batched"), ("async", "Async")))
        rows.append(f'''<li class="success-card" data-record="{record['id']}" value="{rank}"><div class="success-identity"><span class="rank-number" aria-hidden="true">{rank:02d}</span><h3>{model_link(base,record)}</h3></div><dl class="success-scores">{rates}<div><dt>ΔS <small>{t('百分点','pp')}</small></dt><dd class="delta" data-field="delta">{record['delta']:+.1f}</dd></div></dl></li>''')
    mean = paper["mean"]
    return f"""<section class="section success-section" id="task-success"><div class="section-title"><h2>{t('任务成功率','Task success')}</h2>
<label class="inline-filter" data-enhance hidden>{t('排名依据','Rank by')}<select id="success-metric" aria-controls="success-rows"><option value="drs" data-zh="DRS（论文顺序）" data-en="DRS (paper order)">DRS（论文顺序）</option><option value="batched">Batched ↓</option><option value="async">Async ↓</option><option value="delta">ΔS ↓</option></select></label></div>
<p class="ranking-caption">{t('Batched 与 Async 的成功率，按论文顺序排列。','Batched and Async success rates, in paper order.')}</p>
<ol id="success-rows" class="rank-list success-list" role="list" aria-label="Task success leaderboard">{''.join(rows)}</ol>
<aside class="ranking-mean success-mean" data-summary="success-mean"><h3>{t('九模型均值','Nine-agent mean')}</h3><dl class="success-scores"><div><dt>Batched S <small>(%)</small></dt><dd data-field="batched">{mean['batched']:.1f}</dd></div><div><dt>Async S <small>(%)</small></dt><dd data-field="async">{mean['async']:.1f}</dd></div><div><dt>ΔS <small>{t('百分点','pp')}</small></dt><dd class="delta" data-field="delta">{mean['delta']:+.1f}</dd></div></dl></aside>
<p id="success-empty" class="empty-state" hidden>{t('没有匹配的模型。请调整上方搜索。','No matching agents. Adjust the search above.')}</p>
<p class="result-note">{t('ΔS = Async − Batched（百分点），保留论文舍入前计算的差值。','ΔS = Async − Batched (percentage points), preserving the paper’s pre-rounding differences.')}</p></section>"""

def home(base, corpus, paper, trajectories=None):
    stats = ''.join(f'<div><strong>{n}</strong><span>{t(zh,en)}</span></div>' for n, zh, en in [(str(corpus['task_count']),'公开任务','public tasks'), ('5','任务来源','source families'), ('8','异步场景','async scenarios'), ('621','初始子任务','initial subtasks')])
    sources = ''.join(f'<div><dt>{SOURCES[key]}</dt><dd>{count}<span>{t("个任务", "tasks")}</span></dd></div>' for key,count in corpus['source_counts'].items())
    scenarios = ''.join(f'<a href="{base}/tasks/#scenarios"><span class="scenario-index">{i:02d}</span><span>{t(zh,en)}</span><span class="scenario-total">25</span></a>' for i,(_,zh,en,*_) in enumerate(SCENARIOS,1))
    preview = trajectory_section(base) if trajectories else illustrative_section(base)
    return f'''<section class="hero"><h1>Async-RBench</h1><p class="hero-subtitle">Benchmarking Asynchronous Task Execution<br class="desktop-break"> in LLM Agents</p>
<p class="lead">{t('Async-RBench 用 200 个任务测量语言模型代理的异步执行能力：子任务结果陆续到达时，代理能否修正计划、保留有效工作，并完成任务。','Async-RBench evaluates how language-model agents respond to results arriving during execution: revising plans, retaining valid work and completing the task.')}</p>
<div class="actions"><a class="button primary" href="#example">{t('查看案例','View examples')} <span aria-hidden="true">↓</span></a><a class="button" href="{base}/leaderboard/">{t('模型榜单','Leaderboard')}</a><a class="button" href="{REPO}">GitHub ↗</a><a class="text-link" href="{base}/docs/#sources">{t('论文与数据','Paper & data')}</a></div>
<div class="stats hero-stats" aria-label="Benchmark statistics">{stats}</div></section>
{preview}
<section class="section" id="results"><div class="section-title"><div><h2>{t('主要结果','Results')}</h2><p>{t('九个模型在 200 个任务上的 Async DRS；每个任务重复三次。','Async DRS for nine agents across 200 tasks, with three repetitions per task.')}</p></div><a class="button" href="{base}/leaderboard/">{t('完整榜单','Full leaderboard')} →</a></div>{leaderboard(base,paper,True)}
<p class="baseline-note">{t('任务成功率 S 单独报告。九模型均值为 Async 26.0%，Batched 对照基线 29.7%。','Task success S is reported separately: 26.0% for Async and 29.7% for the Batched baseline, averaged over nine agents.')} <a href="{base}/docs/#baseline">{t('实验对照设置','Baseline protocol')} →</a></p></section>
<section class="section overview-section" id="overview"><div class="section-heading"><h2>{t('测评框架','Evaluation framework')}</h2><p>{t('主代理持续工作，子任务结果按控制规则逐个呈现。测评关注代理如何吸收新证据、调整计划，并验证受影响的工作。','The main agent keeps working as subtask results are presented individually under controlled release rules. Evaluation focuses on integrating new evidence, revising plans and verifying affected work.')}</p></div>
<figure class="architecture-figure"><a href="{base}/assets/evaluation-overview.svg" aria-label="Open full evaluation overview"><picture><source media="(max-width: 680px)" srcset="{base}/assets/evaluation-overview-mobile.svg"><img src="{base}/assets/evaluation-overview.svg" width="1440" height="650" alt="Async evaluation: concurrent execution, individual result presentation, replanning and external evaluation"></picture></a><figcaption>{t('Async 主设置 · 最多三个并发子代理；DRS 评估事件响应，S 评估最终任务完成情况。','Async main setting · up to three concurrent subagents; DRS measures event response and S measures task completion.')} <a href="{base}/assets/evaluation-overview.svg" download>SVG ↓</a></figcaption></figure></section>
<section class="section coverage-section" id="coverage"><div class="section-heading"><h2>{t('任务集','Dataset')}</h2><p>{t('每个来源 40 个任务，每个主场景 25 个任务。','40 tasks per source, 25 tasks per primary scenario.')}</p></div><dl class="source-strip">{sources}</dl><div class="scenario-directory">{scenarios}</div><p class="section-end"><a href="{base}/tasks/">{t('浏览全部 200 个任务与公开材料','Browse all 200 tasks and public materials')} →</a></p></section>
<section class="section start-section" id="start"><div><h2>{t('使用 Async-RBench','Using Async-RBench')}</h2><p>{t('公开任务与测评框架可从 GitHub 获取；运行时需另行配置外置 judge。','Public tasks and the evaluation framework are on GitHub. Running the benchmark requires a separate judge bundle.')}</p></div><ul class="project-links"><li><a href="{base}/tasks/">{t('任务材料','Task materials')} ↗</a></li><li><a href="{base}/evaluate/">{t('安装与运行','Installation & evaluation')} ↗</a></li><li><a href="{base}/evaluate/#sharing">{t('提交结果说明','Sharing results')} ↗</a></li><li><a href="{REPO}/blob/main/CITATION.cff">{t('引用','Citation')} ↗</a></li></ul></section>'''


def illustrative_section(base):
    return f'''<section class="section example-section" id="example" data-example="illustrative"><div class="example-intro"><h2>{t('重复结果如何处理','Handling a repeated result')}</h2><p>{t('以重复与重放为例：同一个完成结果被再次呈现，不应导致重复的副作用。','Consider duplication and replay: presenting the same completion again should not repeat its side effects.')}</p><span class="example-label">{t('机制示例 · 非实验轨迹','Illustrative example · not an experimental trace')}</span></div>
<div class="example-story"><article><span>01</span><div><h3>{t('首次呈现','First presentation')}</h3><p>{t('子任务返回结果，主代理将其整合进当前产物。','A subtask returns a result. The main agent integrates it into the working artifact.')}</p></div></article><article><span>02</span><div><h3>{t('同一结果再次呈现','The same completion returns')}</h3><p>{t('新的交付记录指向同一个完成结果，不等于完成了新的工作。','A new delivery occurrence points to the same completion, not new work.')}</p></div></article><article><span>03</span><div><h3>{t('保留有效状态','Preserve the valid state')}</h3><p>{t('识别重复信息，避免再次写入或重建已经完成的部分。','Recognize the duplicate and avoid writing or rebuilding completed work again.')}</p></div></article><article><span>04</span><div><h3>{t('以执行证据评价响应','Evaluate the recorded response')}</h3><p>{t('判分依据实际动作、产物与检查记录，而非代理自称“已处理”。','Evaluation uses actions, artifacts and executed checks, not a claim that the result was handled.')}</p></div></article></div></section>'''

def task_page(base, corpus):
    scenarios = ''.join(f'<div><dt>{t(zh,en)}</dt><dd>{t(zd,ed)}</dd></div>' for _,zh,en,zd,ed in SCENARIOS)
    sources = ''.join(f'<div><dt>{SOURCES[key]}</dt><dd>{count}</dd></div>' for key,count in corpus['source_counts'].items())
    rows = ''.join(f'''<article class="task-entry" data-task="{escape(task['id'])}"><div class="task-meta"><span>{SOURCES[task['source']]}</span><span>{t('中等','Medium') if task['difficulty']=='medium' else t('困难','Hard')} · {task['subtasks']} {t('子任务','subtasks')}</span></div><h3><a href="{task['url']}">{escape(task['title'].removeprefix('Async-RBench source-native rebuild: '))} <span aria-hidden="true">↗</span></a></h3><code class="case-id">{escape(task['id'])}</code></article>''' for task in corpus['tasks'])
    options = ''.join(f'<option value="{key}">{value}</option>' for key,value in SOURCES.items())
    return heading('DATASET','任务集','Dataset','200 个任务，来自五个来源，每个来源 40 个；全部用于论文主实验。','200 tasks from five sources, with 40 per source. All tasks are included in the main experiment.') + f'''
<dl class="source-strip">{sources}</dl><p class="dataset-summary">{t('共 621 个初始子任务；104 个中等任务，96 个困难任务。73 个任务含 2 个子任务，40 个含 3 个，87 个含 4 个或更多。','There are 621 initial subtasks: 104 tasks are medium and 96 hard. Of the 200 tasks, 73 have two initial subtasks, 40 have three, and 87 have four or more.')}</p>
<section class="section catalog"><div class="section-title"><h2>{t('任务目录','Task catalog')}</h2><a href="{base}/data/corpus.json" download>{t('下载 JSON','Download JSON')}</a></div>
<div class="filters" data-enhance hidden><label>{t('标题或编号','Title or ID')}<input type="search" id="task-search" autocomplete="off"></label><label>{t('来源','Source')}<select id="task-source"><option value="" data-zh="全部来源" data-en="All sources">全部来源</option>{options}</select></label><label>{t('难度','Difficulty')}<select id="task-difficulty"><option value="" data-zh="全部难度" data-en="All levels">全部难度</option><option value="medium" data-zh="中等" data-en="Medium">中等</option><option value="hard" data-zh="困难" data-en="Hard">困难</option></select></label><button class="button subtle" id="task-reset" type="button">{t('重置','Reset')}</button></div>
<div class="catalog-caption"><p id="task-count" aria-live="polite">200 / 200 {t('任务','tasks')}</p><span>{t('选择任务，查看仓库中的材料与说明。','Select a task to open its materials and instructions in the repository.')}</span></div><div class="task-grid" id="task-rows" tabindex="0" role="region" aria-label="Public task catalog">{rows}</div><p class="empty-state" id="task-empty" hidden>{t('没有匹配的任务。请调整筛选条件。','No matching tasks. Try different filters.')}</p></section>
<section class="section" id="scenarios"><h2>{t('异步场景','Async scenarios')}</h2><p>{t('八个场景各 25 个任务，每个任务按一个主场景计数。公开目录只提供总体分布，不披露逐任务的私有事件标注。','Each of the eight scenarios contains 25 tasks, with each task counted once under its primary scenario. Only aggregate counts are public; per-task event labels remain private.')}</p><dl class="definition-list">{scenarios}</dl></section>
<section class="section prose"><h2>{t('发布内容与历史标签','Release contents and legacy labels')}</h2><p>{t('每个任务包含 public/、task/ 和 PROVENANCE.md。解答、隐藏测试、事件时序、验证器和实验轨迹不在公开包中。','Each task includes public/, task/ and PROVENANCE.md. Solutions, hidden tests, event schedules, verifiers and experiment traces are not included.')}</p><p>{t('论文另有 47 个独立构造任务，不属于本次发布的 200 个任务。注册表中的 81/30/89 是历史诊断标签，不是论文的校准、开发和测试划分，也不能据此判断任务是否曾用于开发。','The paper reports 47 separate construction tasks outside this 200-task release. The registry’s 81/30/89 counts are legacy diagnostic labels, not calibration, development and test partitions. They do not establish whether a task was previously used during development.')}</p><a href="{REPO}/blob/main/docs/dataset.md">{t('数据集说明','Dataset documentation')}</a></section>'''


def results_page(base, paper):
    header = heading('PAPER RESULTS','论文榜单','Leaderboard','九个模型，200 个任务，每种交付模式重复三次。主代理与子代理使用同一模型。','Nine agents, 200 tasks and three repetitions per delivery mode. Each system uses the same model for its main agent and subagents.')
    context = f'<nav class="results-nav" aria-label="Results sections"><a href="#main-table">{t("DRS 榜单", "DRS leaderboard")}</a><a href="#task-success">{t("任务成功率", "Task success")}</a><a href="{base}/docs/#scoring">{t("指标定义", "Metric definitions")}</a></nav>'
    return header + source_note(base) + context + f'<section id="main-table" class="ranking-section">{leaderboard(base,paper)}</section>' + success_leaderboard(base,paper) + f'''
<section class="section"><h2>{t('DRS 验证与计划重建','DRS validation & plan rebuilding')}</h2><div class="two-col figure-grid"><article>{figure(base,'drs-validation.png','图 3. 相同目标事件上的 Oracle / Native / Frozen。','Figure 3. Oracle / Native / Frozen on the same target events.')}<p>{t('Oracle 为知晓事件要求的参考恢复程序，不是能力匹配的基线。Frozen 使用同一模型在看不到目标结果时生成的后续动作。','Oracle is a reference recovery program with knowledge of event requirements, not a capability-matched baseline. Frozen uses a continuation generated by the same model without the target result.')}</p></article><article>{figure(base,'full-rebuild.png','图 6. Full-rebuild 与 Native 的 DRS 和调用代价。','Figure 6. DRS and call costs under Full-rebuild and Native.')}<p>{t('Full-rebuild 在每次子代理结果呈现后重建剩余计划，同时保留已完成工作。该三模型干预实验独立于主实验。','Full-rebuild reconstructs the remaining plan after each subagent result is presented, while retaining completed work. This three-agent intervention is separate from the main experiment.')}</p></article></div></section>'''


def model_page(base, record):
    return f'<a class="back-link" href="{base}/leaderboard/">← {t("返回论文结果","All paper results")}</a>' + heading('AGENT RESULTS', record['model'], record['model'], '论文表 3、表 4 的聚合结果。','Aggregate results from Tables 3 and 4.', icon=model_icon(base,record)) + f'''
<div class="model-summary"><div class="main-score"><span>Async DRS</span>{score_bar(record['drs'], record['model'] + ' DRS')}<small>{t('固定刻度 0–100','Fixed scale · 0–100')}</small></div><div class="stats"><div><strong>{record['batched']:.1f}%</strong><span>Batched S</span></div><div><strong>{record['async']:.1f}%</strong><span>Async S</span></div><div><strong>{record['delta']:+.1f}</strong><span>ΔS · {t('百分点','pp')}</span></div></div></div>
<section class="section narrow"><h2>{t('场景 DRS','Scenario DRS')}</h2><p class="ranking-caption">{t('均值 ± 样本标准差','Mean ± sample SD')}</p>{scenario_scores(record['scenarios'], detailed=True)}<p class="fine">{t('每场景 25 个任务，每模式 3 次重复；每模型每模式 600 次运行。','25 tasks per scenario, three repetitions per mode; 600 runs per agent per mode.')} {t('平均 Async 调用次数：','Mean Async calls: ')}{record['calls']:.1f}.</p>{source_note(base)}</section>'''


def evaluate_page(base):
    setup = 'git clone https://github.com/pope8zdt/Async-RBench.git\ncd Async-RBench\npython -m venv .venv\n# Activate: .venv\\Scripts\\Activate.ps1 (PowerShell)\n# or: source .venv/bin/activate (bash)\npython -m pip install -e ".[test]"\nasync-rbench validate-public\nasync-rbench list\npython -m pytest -q'
    validate = 'async-rbench validate-judge --judge-root <judge-root>\nasync-rbench certify-release --judge-root <judge-root>'
    manifest = 'async-rbench-eval make-manifest --output manifest.json --repetitions 3 --guidance incentive --seed 2026 --execution-modes linear async --model <model-id> --judge-root <judge-root>'
    run = 'async-rbench-eval run-manifest --manifest manifest.json --output <run-directory> --profile reference_scaffold_api --runtime-mode api_only --config <profile.yaml> --judge-root <judge-root>'
    aggregate = 'async-rbench-eval aggregate --root <run-directory> --manifest manifest.json --output aggregate.json\nasync-rbench-eval audit-run --root <run-directory> --judge-root <judge-root> --output audit.json'
    return heading('RUN LOCALLY','本地评测与结果交流','Evaluation & sharing results','从公开任务到配对实验：准备环境、配置模型，再汇总与审计结果。','From public tasks to paired experiments: prepare the environment, configure the model, then aggregate and audit results.') + f'''
<nav class="results-nav" aria-label="Evaluation steps"><a href="#installation">{t('安装','Install')}</a><a href="#preparation">{t('准备','Prepare')}</a><a href="#running">{t('运行','Run')}</a><a href="#audit">{t('审计','Audit')}</a><a href="#sharing">{t('结果交流','Share results')}</a></nav>
<div class="notice">{t('使用外置运行版 judge、Docker 和模型配置，即可运行这 200 个任务。新运行结果单独记录，网站保留论文报告值。','Use an external judge for new runs, Docker and a model profile to run these 200 tasks. New scores are recorded separately; the website retains paper-reported results.')}</div>
<section class="step" id="installation"><span class="step-number">01</span><div><h2>{t('安装并检查公开任务','Install and validate public tasks')}</h2><p>Python 3.11+ · Git · Docker (Linux containers)</p>{code(setup)}</div></section>
<section class="step" id="preparation"><span class="step-number">02</span><div><h2>{t('准备 judge 与模型配置','Prepare the judge and model profile')}</h2><p>{t('先申请与当前提交匹配的 judge bundle，由维护者确认可用版本及交付方式。申请不代表自动获得权限；请勿在公开 Issue 中上传密钥、隐藏测试或私有轨迹。收到后在本地验证，不能仅凭 v11.0-paper 名称判断兼容性。','Request a judge bundle for your exact commit; the maintainer must confirm availability and delivery. A request does not grant access. Do not post credentials, hidden tests or private traces in an issue. Validate the supplied bundle locally; the v11.0-paper name alone does not establish compatibility.')}</p><div class="actions"><a class="button" href="{REPO}/issues/new?template=judge-access.yml">{t('申请 judge bundle','Request judge access')}</a><a class="text-link" href="{REPO}/blob/main/docs/judge-bundle.md">{t('获取与配置说明','Access and setup guide')}</a></div>{code(validate)}
<p>{t('复制配置模板，在本地填写模型标识和服务地址；密钥只放在环境变量中。论文中主代理与子代理使用同一模型。','Copy the template and fill in model identifiers and your provider URL locally. Keep the key in an environment variable. The paper uses the same model for main and subagents.')}</p><a class="button" href="{base}/data/experiment-profile.template.yaml" download>{t('下载配置模板','Download profile template')}</a><a class="text-link" href="{REPO}/tree/main/configs/model-profiles">{t('查看配置说明','Configuration reference')}</a></div></section>
<section class="step" id="running"><span class="step-number">03</span><div><h2>{t('创建并运行实验','Create and run the experiment')}</h2><p>{t('替换命令中的尖括号占位值。内部键 linear 表示 Batched，不是串行执行。每个模型的完整计划为 1,200 次运行；九模型合计 10,800 次。','Replace angle-bracket placeholders before running. The internal key linear means Batched, not serial execution. A full manifest contains 1,200 runs per agent; nine agents total 10,800.')}</p>{code(manifest)}{code(run)}<p>{t('默认启用容器隔离和适配器合规检查。运行调用模型 API 并产生相应费用；增加 --resume 可继续同一计划。','Container isolation and adapter conformance are enabled by default. Runs use your model API and incur its charges; add --resume to continue the same plan.')}</p></div></section>
<section class="step" id="audit"><span class="step-number">04</span><div><h2>{t('汇总与审计','Aggregate and audit')}</h2>{code(aggregate)}<p>{t('运行汇总在 development_summary 中，逐次得分在各任务的 score.json 中。保留版本、覆盖率和排除原因；基础设施故障不能记为模型失败，缺失结果不能填零。','Run aggregates are in development_summary; per-episode scores are in each score.json. Retain versions, coverage and exclusion reasons. Infrastructure failures must not count as model failures; missing results must not be filled with zeros.')}</p><p>{t('运行版 judge 固定各组件内的等权要求；框架在命令边界采集产物状态，无法识别同一条命令内修改后又恢复的过程。严格的 --official-track 另有完整过程证据要求，不用于上述默认运行。','The runtime judge freezes equal-weight requirements within components. Artifact state is sampled at command boundaries; edits restored within a single command are outside its coverage. Strict --official-track has additional full-window evidence requirements and is not used above.')}</p><a href="{REPO}/blob/main/docs/cli.md">{t('完整命令行文档','Full CLI reference')}</a></div></section>
<section class="sharing-section" id="sharing"><h2>{t('结果交流','Sharing results')}</h2><div class="sharing-flow"><span>{t('确认版本与证据要求','Confirm versions & evidence')}</span><span aria-hidden="true">→</span><span>{t('整理汇总与审计记录','Prepare summaries & audits')}</span><span aria-hidden="true">→</span><span>{t('与维护者核对','Review with maintainers')}</span></div><p>{t('网站展示论文报告值，不提供在线运行、自动判分或自动上榜。提交新结果前，请与维护者确认协议和所需证据；不要公开 API 密钥、隐藏 judge 或私有轨迹。','The website presents paper-reported results, without online execution, scoring or automatic leaderboard submissions. Before contributing results, confirm the protocol and required evidence with maintainers. Do not publish API keys, hidden judges or private traces.')}</p><a class="button" href="{REPO}/issues">{t('联系维护者','Contact maintainers')} ↗</a></section>'''


def docs_page(base):
    obligations = ''.join(f'<article class="panel"><span class="obligation">{symbol}</span><h3>{t(zh,en)}</h3><p>{t(zd,ed)}</p></article>' for symbol,zh,en,zd,ed in [
        ('C','Change · 必要修改','Change','修改被新证据影响的产物或计划。','Revise artifacts or plans affected by new evidence.'),
        ('R','Preserve · 保留有效工作','Preserve','保留依然有效的状态和已完成工作。','Retain state and completed work that remain valid.'),
        ('F','Forbid · 避免禁止行为','Forbid','避免重复副作用、无关回退和其他禁止更改。','Avoid duplicate side effects, unrelated rollbacks and other forbidden changes.'),
        ('V','Verify · 重新验证','Verify','重跑受影响的检查，形成可核查的验证证据。','Repeat affected checks and produce verifiable evidence.')])
    return heading('PROTOCOL','评测协议','Evaluation protocol','动态重规划分数 DRS 评估事件响应，任务成功率 S 评估最终任务完成情况。两项指标分开报告。','Dynamic Replanning Score (DRS) measures responses to events; task success S measures final task completion. The two metrics are reported separately.') + f'''
<nav class="results-nav" aria-label="Protocol sections"><a href="#scoring">{t('如何计分','Scoring')}</a><a href="#aggregation">{t('如何汇总','Aggregation')}</a><a href="#baseline">{t('实验基线','Baseline')}</a><a href="#limits">{t('运行限制','Limits')}</a><a href="#sources">{t('来源与版本','Sources')}</a></nav>
{figure(base,'evaluation-loop.svg','事件响应的证据与判分流程 · 根据论文机制绘制的网站示意。','Event response evidence and evaluation · website schematic of the paper mechanism.')}
<section class="section" id="scoring"><h2>{t('事件响应契约 ERC','Event Response Contract')}</h2><p>{t('每个目标事件都有私有 ERC，定义四类过程要求以及最终结果 O。契约限定应满足的义务，而不强制唯一动作序列。','Each target event has a private ERC defining four process requirements and final outcome O. It specifies obligations, not a unique action sequence.')}</p><div class="obligation-grid">{obligations}</div>
<div class="formula"><span>P = mean(applicable C, R, F, V)</span><strong>DRS = 100 × (P + O) / 2</strong><small>{t('当前每任务一个目标事件；P 与 O 各占 50%。','One target event per task in the current release; P and O each receive 50% weight.')}</small></div>
<p>{t('不适用的过程组件不进入均值，未满足的义务计零。后续修复可以提高结果分，但不会抹去已发生的禁止行为。参与者主动结束而未到达目标事件时，该事件记零；基础设施或构造失败单独排除。','Inapplicable process components are omitted; unmet requirements score zero. Later repairs can improve outcome credit but do not erase forbidden actions. Participant-controlled termination before the target event scores zero; infrastructure or construction failures are excluded separately.')}</p></section>
<section class="section" id="aggregation"><h2>{t('统计与配对','Aggregation and pairing')}</h2><div class="two-col"><article class="panel"><h3>{t('任务成功率 S','Task success S')}</h3><p>{t('最终产物与执行证据满足所有任务目标的运行比例；分别报告 Batched 与 Async。S 不参与 DRS 的加权。','The percentage of runs whose final artifacts and execution evidence satisfy all task goals, reported for Batched and Async separately. S is not blended into DRS.')}</p></article><article class="panel"><h3>{t('八场景等权','Equal scenario weights')}</h3><p>{t('每次重复先对场景内 25 个任务求均值，再报告三次重复均值的平均值与样本标准差。总体 DRS 对八个场景等权平均；排名不代表统计显著性。','For each repetition, average the 25 tasks in a scenario. Report the mean and sample SD of the three repetition-level means. Overall DRS weights all eight scenarios equally; rankings do not imply statistical significance.')}</p></article></div><p>{t('所有 200 个任务 × 九个模型 × 两种交付模式 × 三次重复 = 10,800 次主实验运行。模式间按任务和重复编号配对；环境、任务、验证器版本、模型配置及资源限制保持匹配。','All 200 tasks × nine agents × two delivery modes × three repetitions = 10,800 main-experiment runs. Modes are paired by task and repetition with matched environments, task/verifier versions, model configurations and limits.')}</p></section>
<section class="section" id="baseline"><h2>{t('Batched：实验对照基线','Batched: the experimental baseline')}</h2><p>{t('Async 是论文的主要设置：主代理持续工作，合格结果按控制规则逐个呈现。Batched 仅用于实验对照，等待所有必需子代理工作流结束后整批呈现结果。两者均并发执行子代理，任务、工作流和资源限制相同。DRS 只报告 Async；任务成功率 S 用于与基线比较。','Async is the main setting: the main agent keeps working while eligible results are presented individually under controlled release rules. Batched is the experimental baseline, presenting results together after all required subagent workflows terminate. Both execute subagents concurrently with matched tasks, workflows and resource limits. DRS is reported only for Async; task success S is compared with the baseline.')}</p>{figure(base,'delivery-modes.svg','主设置与实验基线的交付协议示意；不表示实测耗时或加速比。','Delivery protocols for the main setting and experimental baseline; not measured time or speedup.')}</section>
<section class="section" id="limits"><h2>{t('运行限制','Runtime limits')}</h2><div class="table-wrap"><table><tbody>
<tr><th>{t('主代理响应上限','Main-agent response horizon')}</th><td>100</td></tr><tr><th>{t('每次子代理执行响应上限','Responses per subagent execution')}</th><td>40</td></tr><tr><th>{t('每次响应输出 token 上限','Output token cap per response')}</th><td>16,384</td></tr><tr><th>{t('并发子代理限制','Subagent concurrency limit')}</th><td>3</td></tr><tr><th>{t('运行时间上限','Episode time limit')}</th><td>2,400 s</td></tr><tr><th>{t('紧急 token 保险丝','Emergency token fuse')}</th><td>5,000,000 · {t('非计分资源安全退出','unscored resource-safety abort')}</td></tr></tbody></table></div><p class="fine">{t('初始工作流和恢复任务共用三个并发名额，超出部分排队；恢复任务的累计派生次数单独计数。常规步数耗尽仍计分，紧急资源退出不混作任务失败。','Initial workflows and recovery tasks share three live slots; additional work queues. Recovery-spawn totals are counted separately. Normal step exhaustion remains scored; emergency resource aborts are not task failures.')}</p></section>
<section class="section" id="sources"><h2>{t('数据来源','Sources')}</h2><p>{t('榜单数据来自第 26 版论文（2026-09-29）：表 3（第 7 页）、表 4（第 8 页），验证与重建图来自图 3 和图 6。网站保留论文报告值；新测评结果单独记录。','Leaderboard data comes from manuscript v26 (2026-09-29): Table 3 (page 7), Table 4 (page 8), with validation and rebuilding from Figures 3 and 6. The website retains the paper-reported values; new evaluation results are recorded separately.')}</p>
<p>{t('网页下载数据使用 DRS 0–100、成功率百分比与 ΔS 百分点。框架内部的得分字段使用 [0,1]，不可直接混用。差值按论文保留，不从已舍入的显示值重新计算。','Website downloads use DRS on 0–100, task success in percent and ΔS in percentage points. Framework score fields use [0,1]; do not mix these scales. Differences are preserved from the paper, not recomputed from rounded display values.')}</p>
<p>{t('任务目录由当前公开注册表和发布清单自动生成；逐任务事件标签、解答、隐藏测试与判分真值均不发布。旧实验诊断值不合并进论文榜单；历史版本仍可在 Git 提交记录中追溯。','The catalog is generated from the current public registry and release manifest. Per-task event labels, solutions, hidden tests and scoring truth are not published. Old diagnostic values are not merged into the paper table; historical versions remain in Git history.')}</p>
<div class="actions"><a class="button" href="{base}/data/leaderboard.json" download>{t('下载论文报告值及来源','Download reported values & provenance')}</a><a class="button" href="{REPO}/blob/main/paper_artifacts/experiment_manifest.json">{t('实验清单','Experiment manifest')}</a></div></section>
<section class="section"><h2>{t('文档与引用','Documentation & citation')}</h2><ul class="resource-list"><li><a href="{REPO}/blob/main/docs/protocol.md">{t('评测协议','Evaluation protocol')}</a></li><li><a href="{REPO}/blob/main/docs/adapter-protocol.md">{t('适配器协议','Adapter protocol')}</a></li><li><a href="{REPO}/blob/main/docs/dataset.md">{t('数据集与历史标签','Dataset & legacy labels')}</a></li><li><a href="{REPO}/blob/main/CITATION.cff">{t('引用信息','Citation metadata')}</a></li><li><a href="{REPO}/blob/main/THIRD_PARTY_LICENSES.md">{t('任务材料来源许可','Task-material licenses')}</a></li></ul><p class="fine">{t('代码与文档使用 Apache-2.0；转换后的任务材料遵循对应上游条款。作者信息在双盲审稿期间保持匿名。','Code and documentation use Apache-2.0; transformed task materials retain upstream terms. Author information remains anonymized during double-blind review.')}</p></section>'''


def trajectory_section(base):
    return f'''<section class="section trajectory-section" id="example" data-example="recorded">
<div class="section-title"><div><h2>{t('运行案例','Trajectory examples')}</h2><p>{t('三条真实运行记录。选择案例，回看结果到达前后的动作。','Three recorded runs. Select a case to follow the actions before and after results arrive.')}</p></div><span class="local-preview-tag">{t('本地预览','Local preview')}</span></div>
<div id="trajectory-player" class="trace-player" data-src="{base}/data/trajectories.local.json" aria-label="Trajectory replay"><p class="trace-loading" role="status">{t('正在读取本地回放数据…','Loading local replay data…')}</p></div>
<p class="trace-scope">{t('归档日志节选；时间与事件编号保持原样，回放时压缩等待。','Selected archived records; original times and event IDs are preserved. Playback compresses idle time.')}</p>
<noscript><p>{t('动态回放需要 JavaScript；上方测评说明和下方论文结果仍可阅读。','Replay requires JavaScript. The overview and paper results remain readable.')}</p></noscript></section>'''


def render_pages(base, corpus, paper, trajectories=None):
    payload = json.dumps({"paper": paper, "tasks": corpus['tasks']}, ensure_ascii=False).replace('<', '\\u003c')
    data = f'<script id="site-data" type="application/json">{payload}</script>'
    homepage = home(base,corpus,paper,trajectories)
    routes = {
        "": ("Overview", homepage), "tasks/": ("Tasks", task_page(base,corpus)),
        "leaderboard/": ("Paper results", results_page(base,paper)),
        "evaluate/": ("Run the benchmark", evaluate_page(base)), "docs/": ("Protocol", docs_page(base)),
    }
    for record in paper['records']:
        routes[f"runs/{record['id']}/"] = (record['model'], model_page(base,record))
    pages = {f"{route}index.html": document(base,route,title,body+data) for route,(title,body) in routes.items()}
    archived = heading('ARCHIVED LINK','历史结果','Historical results','此链接属于早期实验记录，未纳入当前论文结果。原始记录可在仓库历史中查看。','This link refers to an earlier experiment, not part of the current paper results. The original record remains in repository history.')
    archived += f'<div class="actions"><a class="button primary" href="{base}/leaderboard/">{t("查看论文结果","Current paper results")} →</a><a class="button" href="{REPO}/tree/19e21e50fbea45812a3d845e1ade8c3a842ca9a9/website">{t("查看历史网站源码","Historical website source")}</a></div>'
    missing = heading('404','页面不存在','Page not found','请检查地址，或从首页继续浏览。','Check the address or return to the overview.') + f'<a class="button" href="{base}/">{t("返回首页","Back to overview")}</a>'
    pages['404.html'] = document(base,'404.html','Page not found',missing)
    # Keep old published result links useful without relabeling them as paper runs.
    for old_id in ('e87590fa970dc29a','c484afc989d4a191','dfbf12394889e1f1','e4c241be482abb98'):
        pages[f'runs/{old_id}/index.html'] = document(base,'','Historical record',archived)
    return pages
