"""Readable HTML is the default; JavaScript only enhances controls."""
from html import escape
import json

REPO = "https://github.com/pope8zdt/Async-RBench"
SOURCES = {"gaia2": "GAIA2", "multiagentbench": "MultiAgentBench", "osworld": "OSWorld", "swe-bench": "SWE-bench", "terminal-bench": "Terminal-Bench"}
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
    nav = [("", "首页", "Overview"), ("tasks/", "任务", "Tasks"), ("leaderboard/", "榜单", "Results"), ("evaluate/", "运行", "Run"), ("docs/", "协议", "Protocol")]
    links = ''.join(f'<a href="{base}/{path}" {"aria-current=page" if route == path else ""}>{t(zh,en)}</a>' for path, zh, en in nav)
    return f'''<!doctype html>
<html lang="zh" data-theme="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Async-RBench: 200 tasks for asynchronous task execution in LLM agents. Paper results, public tasks and evaluation protocol.">
<meta name="color-scheme" content="light dark"><title>{escape(title)} · Async-RBench</title>
<link rel="stylesheet" href="{base}/assets/site.css">
<script>try{{const p=JSON.parse(localStorage.getItem('async-rbench-paper-preferences')||'{{}}');document.documentElement.lang=p.language==='en'?'en':'zh';document.documentElement.dataset.theme=p.theme==='dark'||(!p.theme&&matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light'}}catch{{}}</script>
<script type="module" src="{base}/assets/site.mjs"></script></head>
<body data-base="{base}" class="{'leaderboard-page' if route == 'leaderboard/' else ''}"><a class="skip-link" href="#main">{t('跳转到内容','Skip to content')}</a>
<header class="site-header"><div class="header-inner"><a class="brand" href="{base}/">Async-RBench</a>
<nav aria-label="Main navigation">{links}</nav><div class="preferences" hidden data-enhance>
<button id="language" type="button">English</button><button id="theme" type="button">{t('深色','Dark')}</button></div></div></header>
<main id="main" tabindex="-1">{body}</main>
<footer><a class="brand" href="{base}/">Async-RBench</a><span>{t('200 个任务 · v11.0-paper','200 tasks · v11.0-paper')}</span>
<a href="{REPO}">GitHub</a><a href="{base}/docs/#sources">{t('数据与说明','Sources & scope')}</a></footer>
<noscript><p class="noscript">页面内容无需 JavaScript 即可阅读。筛选、切换语言与主题需要启用 JavaScript。 / All content is readable without JavaScript. Enable it for filters, language and theme controls.</p></noscript>
</body></html>'''


def figure(base, name, zh, en):
    return f'<figure><a href="{base}/assets/{name}" aria-label="{escape(en)}"><img src="{base}/assets/{name}" alt="{escape(en)}" loading="lazy"></a><figcaption>{t(zh,en)}</figcaption></figure>'


def heading(label, zh, en, lead_zh, lead_en):
    return f'<section class="page-heading"><h1>{t(zh,en)}</h1><p class="lead">{t(lead_zh,lead_en)}</p></section>'


def source_note(base, table=None):
    zh = f'来源：2026-09-26 论文稿，表 {table}。' if table else '来源：2026-09-26 论文稿，表 3、表 4。'
    en = f'Source: manuscript dated 2026-09-26, Table {table}.' if table else 'Source: manuscript dated 2026-09-26, Tables 3 and 4.'
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


def scenario_disclosure(scenarios, calls, label_zh, label_en, maxima=None):
    return f'''<details class="rank-details"><summary class="rank-toggle"><span class="sr-only">{t(label_zh + '：八场景成绩', label_en + ': eight scenario scores')}</span><span class="disclosure-icon" aria-hidden="true"></span></summary>
{scenario_scores(scenarios, maxima)}<dl class="call-count"><dt>Calls</dt><dd data-field="calls">{calls:.1f}</dd></dl></details>'''


def result_rows(base, paper):
    maxima = {key: max(r["scenarios"][key]["mean"] for r in paper["records"]) for key in paper["scenario_order"]}
    rows = []
    for rank, record in enumerate(sorted(paper["records"], key=lambda r: -r["drs"]), 1):
        label = record.get('paper_label', record['model'])
        rows.append(f'''<li class="rank-card" data-record="{record['id']}" data-place="{rank}" value="{rank}"><article>
<div class="rank-card-heading"><span class="rank-number" aria-hidden="true">{rank:02d}</span><div class="rank-identity"><h3><a href="{base}/runs/{record['id']}/">{escape(label)}</a></h3></div>
<div class="rank-score"><span class="score-label">DRS <small>/ 100</small></span>{score_bar(record['drs'], record['model'] + ' DRS')}</div></div>
{scenario_disclosure(record['scenarios'], record['calls'], label, label, maxima)}</article></li>''')
    return ''.join(rows)


def leaderboard(base, paper, compact=False):
    scenario_options = ''.join(f'<option value="{key}">{SCENARIO_LABELS[key]} ↓</option>' for key in paper["scenario_order"])
    controls = '' if compact else f"""<div class="filters result-filters" data-enhance hidden><label>{t('搜索模型','Search agents')}<input id="model-search" type="search" autocomplete="off" aria-controls="result-rows success-rows"></label>
<label>{t('排名依据','Rank by')}<select id="metric" aria-controls="result-rows"><option value="drs">DRS ↓</option>{scenario_options}</select></label>
<div class="result-downloads"><a href="{base}/data/leaderboard.json" download>JSON</a><a href="{base}/data/leaderboard.csv" download>CSV</a></div></div>"""
    mean = paper['mean']
    return f"""{controls}<p class="ranking-caption">{t('点击右侧箭头展开八场景成绩（均值 ± 样本标准差）与 Calls。','Use the arrows to expand eight scenario scores (mean ± sample SD) and Calls.')}</p>
<ol id="result-rows" class="rank-list" role="list" aria-label="DRS leaderboard">{result_rows(base,paper)}</ol>
<p id="result-empty" class="empty-state" role="status" hidden>{t('没有匹配的模型。请尝试其他关键词。','No matching agents. Try another search.')}</p>
<aside class="ranking-mean drs-mean" data-summary="drs-mean"><div class="rank-card-heading"><div class="rank-identity"><h3>{t('九模型均值','Nine-agent mean')}</h3></div><div class="rank-score"><span class="score-label">DRS <small>/ 100</small></span>{score_bar(mean['drs'], 'Mean DRS')}</div></div>{scenario_disclosure(mean['scenarios'], mean['calls'], '九模型均值', 'Nine-agent mean')}</aside>
<div class="ranking-notes"><p>{t('粗体标出各场景最高分。Calls 是每次 Async 运行中主代理与全部子代理的平均响应总数，不是得分。','Bold marks the best score in each scenario. Calls is the mean number of main-agent and subagent responses per Async run, not a score.')}</p>
<p>{t('DRS 条统一采用 0–100 刻度。点击模型名称可查看详情。','DRS bars use a fixed 0–100 scale. Open an agent for its detail view.')}</p></div>{source_note(base,3)}"""


def success_leaderboard(base, paper):
    rows = []
    maxima = {key: max(r[key] for r in paper["records"]) for key in ("batched", "async")}
    for rank, record in enumerate(sorted(paper["records"], key=lambda r: -r["drs"]), 1):
        rates = ''.join(f'<div><dt>{label} S <small>(%)</small></dt><dd data-field="{key}"><{"strong" if record[key] == maxima[key] else "span"}>{record[key]:.1f}</{"strong" if record[key] == maxima[key] else "span"}></dd></div>' for key, label in (("batched", "Batched"), ("async", "Async")))
        rows.append(f'''<li class="success-card" data-record="{record['id']}" value="{rank}"><div class="success-identity"><span class="rank-number" aria-hidden="true">{rank:02d}</span><h3><a href="{base}/runs/{record['id']}/">{escape(record.get('paper_label', record['model']))}</a></h3></div><dl class="success-scores">{rates}<div><dt>ΔS <small>{t('百分点','pp')}</small></dt><dd class="delta" data-field="delta">{record['delta']:+.1f}</dd></div></dl></li>''')
    mean = paper["mean"]
    return f"""<section class="section success-section" id="task-success"><div class="section-title"><h2>{t('任务成功率','Task success')}</h2>
<label class="inline-filter" data-enhance hidden>{t('排名依据','Rank by')}<select id="success-metric" aria-controls="success-rows"><option value="drs" data-zh="DRS（论文顺序）" data-en="DRS (paper order)">DRS（论文顺序）</option><option value="batched">Batched ↓</option><option value="async">Async ↓</option><option value="delta">ΔS ↓</option></select></label></div>
<p class="ranking-caption">{t('Batched 与 Async 的任务成功率，与 DRS 分开报告。默认沿用论文的 DRS 排序。','Task success under Batched and Async delivery, reported separately from DRS. Default order follows the paper’s DRS ranking.')}</p>
<ol id="success-rows" class="rank-list success-list" role="list" aria-label="Task success leaderboard">{''.join(rows)}</ol>
<aside class="ranking-mean success-mean" data-summary="success-mean"><h3>{t('九模型均值','Nine-agent mean')}</h3><dl class="success-scores"><div><dt>Batched S <small>(%)</small></dt><dd data-field="batched">{mean['batched']:.1f}</dd></div><div><dt>Async S <small>(%)</small></dt><dd data-field="async">{mean['async']:.1f}</dd></div><div><dt>ΔS <small>{t('百分点','pp')}</small></dt><dd class="delta" data-field="delta">{mean['delta']:+.1f}</dd></div></dl></aside>
<p id="success-empty" class="empty-state" hidden>{t('没有匹配的模型。请调整上方搜索。','No matching agents. Adjust the search above.')}</p>
<p class="fine">{t('ΔS = Async − Batched，单位为百分点。差值沿用论文按未舍入数据计算的结果，不从显示值重新相减。','ΔS = Async − Batched, in percentage points. Differences retain the paper’s pre-rounding calculations rather than subtracting displayed rates.')}</p>{source_note(base,4)}</section>"""

def home(base, corpus, paper):
    stats = ''.join(f'<div><strong>{n}</strong><span>{t(zh,en)}</span></div>' for n, zh, en in [(str(corpus['task_count']),'任务','tasks'), ('8','异步场景','async scenarios'), ('9','模型','agents'), ('10,800','主实验运行','main-experiment runs')])
    return f'''<section class="hero"><h1>Async-RBench</h1><p class="hero-subtitle">Benchmarking Asynchronous Task Execution in LLM Agents</p>
<p class="lead">{t('当子代理的结果陆续返回，主代理能否正确调整后续工作？Async-RBench 在八类异步场景中，评测代理如何修改计划、保留有效成果并完成必要验证。','Can an agent revise its work as subagent results arrive? Async-RBench evaluates plan revision, preservation of valid work and verification across eight asynchronous scenarios.')}</p>
<div class="stats hero-stats" aria-label="Benchmark statistics">{stats}</div>
<div class="actions"><a class="button primary" href="#results">{t('查看榜单','View leaderboard')}</a><a class="button" href="{REPO}">{t('代码与任务集','Code & dataset')}</a><a class="button" href="{base}/docs/">{t('评测协议','Evaluation protocol')}</a></div></section>
<section class="section overview-section" id="overview"><div class="section-intro"><h2>{t('评测什么','What the benchmark measures')}</h2><p>{t('结果不再一次性到齐。代理需要判断何时等待、何时修改，以及哪些工作可以保留。','Results do not arrive all at once. Agents must decide when to wait, what to revise and which work remains valid.')}</p></div>
{figure(base,'overview.png','图 1. 异步执行中的结果整合与重规划。','Figure 1. Result integration and replanning during asynchronous execution.')}</section>
<section class="section" id="results"><div class="section-title"><div><h2>{t('论文榜单','Paper leaderboard')}</h2><p>{t('九个模型，按动态重规划分数 DRS 排序。','Nine agents ranked by Dynamic Replanning Score (DRS).')}</p></div><a href="{base}/leaderboard/">{t('完整榜单与场景结果','Full leaderboard & scenario results')} →</a></div>{leaderboard(base,paper,True)}</section>
<section class="section"><div class="section-intro"><h2>{t('主要发现','What we found')}</h2></div><div class="findings">
<article><span class="finding-number">01</span><h3>{t('异步响应仍有明显缺口','Room for better event responses')}</h3><p>{t('九个模型的 Async DRS 为 19.2–45.1。重复结果和子代理失败是平均得分最低的两个场景。','Async DRS ranges from 19.2 to 45.1 across nine agents. Duplication and replay, and subagent failure, have the lowest mean scenario scores.')}</p></article>
<article><span class="finding-number">02</span><h3>{t('更早收到结果，不保证更高成功率','Earlier results do not ensure success')}</h3><p>{t('在论文协议下，九模型的 Async 任务成功率点估计均低于 Batched，平均成功率从 29.7% 降至 26.0%。这一比较不代表所有异步系统的因果结论。','Under the paper protocol, all nine agents have lower task-success point estimates with Async delivery. Mean success falls from 29.7% to 26.0%. This comparison does not establish a causal claim about asynchronous systems in general.')}</p></article>
<article><span class="finding-number">03</span><h3>{t('重建计划有收益，也有代价','Replanning has benefits and costs')}</h3><p>{t('要求 Terra、Luna 和 Gemini 在收到结果后重建剩余计划，DRS 分别从 39.7、31.1、19.2 升至 42.3、34.6、21.9。论文正文报告调用次数增加 7.5–10.2%；图文数值差异见结果页。','Requiring Terra, Luna and Gemini to rebuild the remaining plan after a result arrives raises DRS from 39.7, 31.1 and 19.2 to 42.3, 34.6 and 21.9, respectively. The paper text reports 7.5–10.2% more calls; a figure/text discrepancy is noted on the results page.')}</p></article></div></section>
<section class="section"><h2>{t('两种结果交付模式','Result delivery modes')}</h2><div class="two-col text-columns"><article><h3>Batched</h3><p>{t('子代理并行执行。所有必需工作流结束后，结果一次性交给主代理。','Subagents run concurrently. Results are presented together after all required workflows terminate.')}</p></article><article><h3>Async</h3><p>{t('主代理继续工作，控制器在约定任务状态下逐个交付合格结果。主代理自行判断是否以及如何修改后续计划。','The main agent continues working while the controller presents eligible results at predefined task states. The agent decides whether and how to revise its remaining plan.')}</p></article></div><p class="fine">{t('两种模式使用相同任务、工作流和资源限制，但分别运行子代理，生成结果与后续动作可能不同。','Both modes use the same tasks, workflows and resource limits. Subagents execute separately in each mode, so generated results and subsequent actions may differ.')}</p></section>

<section class="section resource-section"><div><h2>{t('使用 Async-RBench','Work with Async-RBench')}</h2><p>{t('浏览公开任务，了解判分协议，或在本地配置测评。','Explore the public tasks, inspect the scoring protocol or set up a local evaluation.')}</p></div><ul class="resource-list"><li><a href="{base}/tasks/">{t('任务目录','Task catalog')} →</a></li><li><a href="{base}/evaluate/">{t('安装与运行','Installation & evaluation')} →</a></li><li><a href="{REPO}/blob/main/CITATION.cff">{t('引用信息','Citation metadata')} →</a></li></ul></section>'''

def task_page(base, corpus):
    scenarios = ''.join(f'<div><dt>{t(zh,en)}</dt><dd>{t(zd,ed)}</dd></div>' for _,zh,en,zd,ed in SCENARIOS)
    sources = ''.join(f'<div><dt>{SOURCES[key]}</dt><dd>{count}</dd></div>' for key,count in corpus['source_counts'].items())
    rows = ''.join(f'''<tr data-task="{escape(task['id'])}"><th scope="row"><a href="{task['url']}">{escape(task['title'].removeprefix('Async-RBench source-native rebuild: '))}</a><code class="case-id">{escape(task['id'])}</code></th><td>{SOURCES[task['source']]}</td><td>{t('中等','Medium') if task['difficulty']=='medium' else t('困难','Hard')}</td><td>{task['subtasks']}</td></tr>''' for task in corpus['tasks'])
    options = ''.join(f'<option value="{key}">{value}</option>' for key,value in SOURCES.items())
    return heading('DATASET','任务集','Dataset','200 个任务，来自五个来源，每个来源 40 个；全部用于论文主实验。','200 tasks from five sources, with 40 per source. All tasks are included in the main experiment.') + f'''
<dl class="source-strip">{sources}</dl><p class="dataset-summary">{t('共 621 个初始子任务；104 个中等任务，96 个困难任务。73 个任务含 2 个子任务，40 个含 3 个，87 个含 4 个或更多。','There are 621 initial subtasks: 104 tasks are medium and 96 hard. Of the 200 tasks, 73 have two initial subtasks, 40 have three, and 87 have four or more.')}</p>
<section class="section catalog"><div class="section-title"><h2>{t('任务目录','Task catalog')}</h2><a href="{base}/data/corpus.json" download>{t('下载 JSON','Download JSON')}</a></div>
<div class="filters" data-enhance hidden><label>{t('标题或编号','Title or ID')}<input type="search" id="task-search" autocomplete="off"></label><label>{t('来源','Source')}<select id="task-source"><option value="" data-zh="全部来源" data-en="All sources">全部来源</option>{options}</select></label><label>{t('难度','Difficulty')}<select id="task-difficulty"><option value="" data-zh="全部难度" data-en="All levels">全部难度</option><option value="medium" data-zh="中等" data-en="Medium">中等</option><option value="hard" data-zh="困难" data-en="Hard">困难</option></select></label><button class="button subtle" id="task-reset" type="button">{t('重置','Reset')}</button></div>
<p class="fine" id="task-count" aria-live="polite">200 / 200 {t('任务','tasks')}</p><div class="table-wrap task-table" tabindex="0" role="region" aria-label="Public task catalog"><table><thead><tr><th>{t('任务','Task')}</th><th>{t('来源','Source')}</th><th>{t('难度','Difficulty')}</th><th>{t('子任务数','Subtasks')}</th></tr></thead><tbody id="task-rows">{rows}</tbody></table></div><p class="empty-state" id="task-empty" hidden>{t('没有匹配的任务。请调整筛选条件。','No matching tasks. Try different filters.')}</p><p class="fine">{t('任务链接指向仓库中的原始材料。网页标题省略了重复前缀，任务编号与下载数据不变。','Task links open the original materials in the repository. Display titles omit a repeated prefix; identifiers and downloaded metadata are unchanged.')}</p></section>
<section class="section" id="scenarios"><h2>{t('异步场景','Async scenarios')}</h2><p>{t('八个场景各 25 个任务，每个任务按一个主场景计数。公开目录只提供总体分布，不披露逐任务的私有事件标注。','Each of the eight scenarios contains 25 tasks, with each task counted once under its primary scenario. Only aggregate counts are public; per-task event labels remain private.')}</p><dl class="definition-list">{scenarios}</dl></section>
<section class="section prose"><h2>{t('发布内容与历史标签','Release contents and legacy labels')}</h2><p>{t('每个任务包含 public/、task/ 和 PROVENANCE.md。解答、隐藏测试、事件时序、验证器和实验轨迹不在公开包中。','Each task includes public/, task/ and PROVENANCE.md. Solutions, hidden tests, event schedules, verifiers and experiment traces are not included.')}</p><p>{t('论文另有 47 个独立构造任务，不属于本次发布的 200 个任务。注册表中的 81/30/89 是历史诊断标签，不是论文的校准、开发和测试划分，也不能据此判断任务是否曾用于开发。','The paper reports 47 separate construction tasks outside this 200-task release. The registry’s 81/30/89 counts are legacy diagnostic labels, not calibration, development and test partitions. They do not establish whether a task was previously used during development.')}</p><a href="{REPO}/blob/main/docs/dataset.md">{t('数据集说明','Dataset documentation')}</a></section>'''


def results_page(base, paper):
    header = heading('PAPER RESULTS','论文榜单','Leaderboard','九个模型，200 个任务，每种交付模式重复三次。主代理与子代理使用同一模型。','Nine agents, 200 tasks and three repetitions per delivery mode. Each system uses the same model for its main agent and subagents.')
    context = f'<nav class="results-nav" aria-label="Results sections"><a href="#main-table">{t("DRS 榜单", "DRS leaderboard")}</a><a href="#task-success">{t("任务成功率", "Task success")}</a><a href="{base}/docs/#scoring">{t("指标定义", "Metric definitions")}</a></nav>'
    return header + context + f'<section id="main-table" class="ranking-section">{leaderboard(base,paper)}</section>' + success_leaderboard(base,paper) + f'''<p class="fine">{t('每场景包含 25 个任务，总体 DRS 对八场景等权平均。排名不代表统计显著性。','Each scenario contains 25 tasks; overall DRS weights all eight scenarios equally. Rankings do not imply statistical significance.')}</p>
<section class="section"><h2>{t('DRS 验证与计划重建','DRS validation & plan rebuilding')}</h2><div class="two-col figure-grid"><article>{figure(base,'drs-validation.png','图 3. 相同目标事件上的 Oracle / Native / Frozen。','Figure 3. Oracle / Native / Frozen on the same target events.')}<p>{t('Oracle 为知晓事件要求的参考恢复程序，不是能力匹配的基线。Frozen 使用同一模型在看不到目标结果时生成的后续动作。','Oracle is a reference recovery program with knowledge of event requirements, not a capability-matched baseline. Frozen uses a continuation generated by the same model without the target result.')}</p></article><article>{figure(base,'full-rebuild.png','图 6. Full-rebuild 与 Native 的 DRS 和调用代价。','Figure 6. DRS and call costs under Full-rebuild and Native.')}<p>{t('Full-rebuild 在每次子代理结果交付后重建剩余计划，同时保留已完成工作。该三模型干预实验独立于主实验。','Full-rebuild reconstructs the remaining plan after each subagent result while retaining completed work. This three-agent intervention is separate from the main experiment.')}</p><p class="fine">{t('图 6 取自论文原稿，Gemini Native 的子代理调用数为 55.5。图中调用数与正文报告的 7.5–10.2% 增幅不能完全对应；此处均保留原值。','Figure 6 is taken from the manuscript, where Gemini Native has 55.5 subagent calls. The plotted counts do not fully reconcile with the text’s reported 7.5–10.2% increase; both are retained as reported.')}</p></article></div></section>'''


def model_page(base, record):
    return f'<a class="back-link" href="{base}/leaderboard/">← {t("返回论文结果","All paper results")}</a>' + heading('AGENT RESULTS', record['model'], record['model'], '论文表 3、表 4 的聚合结果。','Aggregate results from Tables 3 and 4.') + f'''
<div class="model-summary"><div class="main-score"><span>Async DRS</span>{score_bar(record['drs'], record['model'] + ' DRS')}<small>{t('固定刻度 0–100','Fixed scale · 0–100')}</small></div><div class="stats"><div><strong>{record['batched']:.1f}%</strong><span>Batched S</span></div><div><strong>{record['async']:.1f}%</strong><span>Async S</span></div><div><strong>{record['delta']:+.1f}</strong><span>ΔS · {t('百分点','pp')}</span></div></div></div>
<section class="section narrow"><h2>{t('场景 DRS','Scenario DRS')}</h2><p class="ranking-caption">{t('均值 ± 样本标准差','Mean ± sample SD')}</p>{scenario_scores(record['scenarios'], detailed=True)}<p class="fine">{t('每场景 25 个任务，每模式 3 次重复；每模型每模式 600 次运行。','25 tasks per scenario, three repetitions per mode; 600 runs per agent per mode.')} {t('平均 Async 调用次数：','Mean Async calls: ')}{record['calls']:.1f}.</p>{source_note(base)}</section>'''


def evaluate_page(base):
    setup = 'git clone https://github.com/pope8zdt/Async-RBench.git\ncd Async-RBench\npython -m venv .venv\n# Activate: .venv\\Scripts\\Activate.ps1 (PowerShell)\n# or: source .venv/bin/activate (bash)\npython -m pip install -e ".[test]"\nasync-rbench validate-public\nasync-rbench list\npython -m pytest -q'
    validate = 'async-rbench validate-judge --judge-root <judge-root>\nasync-rbench certify-release --judge-root <judge-root>'
    manifest = 'async-rbench-eval make-manifest --output manifest.json --repetitions 3 --guidance incentive --seed 2026 --execution-modes linear async --model <model-id> --judge-root <judge-root>'
    run = 'async-rbench-eval run-manifest --manifest manifest.json --output <run-directory> --profile reference_scaffold_api --runtime-mode api_only --config <profile.yaml> --official-track --judge-root <judge-root>'
    aggregate = 'async-rbench-eval aggregate --root <run-directory> --manifest manifest.json --output aggregate.json\nasync-rbench-eval audit-run --root <run-directory> --output audit.json'
    return heading('RUN LOCALLY','运行测评','Run the benchmark','在本地安装公开框架，检查任务材料，并运行配对实验。','Install the public framework locally, inspect the tasks and run paired experiments.') + f'''
<div class="notice">{t('检查公开任务需要 Python 3.11+ 和 Git。正式判分还需要匹配版本的外置 judge、Docker 和模型 API；仅下载仓库不能复现正式分数。','Inspecting public tasks requires Python 3.11+ and Git. Formal scoring also requires a matching external judge, Docker and a model API. The repository alone cannot reproduce formal scores.')}</div>
<section class="step"><span class="step-number">01</span><div><h2>{t('安装并检查公开任务','Install and validate public tasks')}</h2><p>Python 3.11+ · Git</p>{code(setup)}</div></section>
<section class="step"><span class="step-number">02</span><div><h2>{t('准备 judge 与模型配置','Prepare the judge and model profile')}</h2><p>{t('取得与 v11.0-paper 匹配的 judge bundle 后，在本地验证。网站不提供隐藏判分材料。','After obtaining the judge bundle matching v11.0-paper, validate it locally. Hidden scoring materials are not distributed on this website.')}</p>{code(validate)}
<p>{t('复制配置模板，在本地填写模型标识和服务地址；密钥只放在环境变量中。论文中主代理与子代理使用同一模型。','Copy the template and fill in model identifiers and your provider URL locally. Keep the key in an environment variable. The paper uses the same model for main and subagents.')}</p><a class="button" href="{base}/data/experiment-profile.template.yaml" download>{t('下载配置模板','Download profile template')}</a><a class="text-link" href="{REPO}/tree/main/configs/model-profiles">{t('查看配置说明','Configuration reference')}</a></div></section>
<section class="step"><span class="step-number">03</span><div><h2>{t('创建并运行实验','Create and run the experiment')}</h2><p>{t('替换命令中的尖括号占位值。内部键 linear 表示 Batched，不是串行执行。每个模型的完整计划为 1,200 次运行；九模型合计 10,800 次。','Replace angle-bracket placeholders before running. The internal key linear means Batched, not serial execution. A full manifest contains 1,200 runs per agent; nine agents total 10,800.')}</p>{code(manifest)}{code(run)}<p class="fine">{t('运行会调用模型 API 并产生相应费用。正式模式检查隔离、资源配置与适配器合规。','Execution uses your model API and incurs its charges. Official mode checks isolation, resource configuration and adapter conformance.')}</p></div></section>
<section class="step"><span class="step-number">04</span><div><h2>{t('汇总与审计','Aggregate and audit')}</h2>{code(aggregate)}<p>{t('保留版本、配置、覆盖率和排除原因；基础设施故障不能记为模型失败，缺失结果不能填零。','Retain versions, configurations, coverage and exclusion reasons. Infrastructure failures must not count as model failures; missing results must not be filled with zeros.')}</p><a href="{REPO}/blob/main/docs/cli.md">{t('完整命令行文档','Full CLI reference')}</a></div></section>
<section class="panel"><h2>{t('结果提交','Sharing results')}</h2><p>{t('网站展示论文报告值，不提供在线运行、自动判分或自动上榜。提交新结果前，请与维护者确认协议和所需证据；不要公开 API 密钥、隐藏 judge 或私有轨迹。','The website presents paper-reported results, without online execution, scoring or automatic leaderboard submissions. Before contributing results, confirm the protocol and required evidence with maintainers. Do not publish API keys, hidden judges or private traces.')}</p><a href="{REPO}/issues">{t('联系维护者','Contact maintainers')}</a></section>'''


def docs_page(base):
    obligations = ''.join(f'<article class="panel"><span class="obligation">{symbol}</span><h3>{t(zh,en)}</h3><p>{t(zd,ed)}</p></article>' for symbol,zh,en,zd,ed in [
        ('C','Change · 必要修改','Change','修改被新证据影响的产物或计划。','Revise artifacts or plans affected by new evidence.'),
        ('R','Preserve · 保留有效工作','Preserve','保留依然有效的状态和已完成工作。','Retain state and completed work that remain valid.'),
        ('F','Forbid · 避免禁止行为','Forbid','避免重复副作用、无关回退和其他禁止更改。','Avoid duplicate side effects, unrelated rollbacks and other forbidden changes.'),
        ('V','Verify · 重新验证','Verify','重跑受影响的检查，形成可核查的验证证据。','Repeat affected checks and produce verifiable evidence.')])
    return heading('PROTOCOL','评测协议','Evaluation protocol','动态重规划分数 DRS 评估事件响应，任务成功率 S 评估最终任务完成情况。两项指标分开报告。','Dynamic Replanning Score (DRS) measures responses to events; task success S measures final task completion. The two metrics are reported separately.') + f'''
{figure(base,'benchmark-mechanism.png','图 2. 控制器、结果交付与 ERC 判分。','Figure 2. Controller, result presentation and ERC scoring.')}
<section class="section" id="scoring"><h2>{t('事件响应契约 ERC','Event Response Contract')}</h2><p>{t('每个目标事件都有私有 ERC，定义四类过程要求以及最终结果 O。契约限定应满足的义务，而不强制唯一动作序列。','Each target event has a private ERC defining four process requirements and final outcome O. It specifies obligations, not a unique action sequence.')}</p><div class="obligation-grid">{obligations}</div>
<div class="formula"><span>P = mean(applicable C, R, F, V)</span><strong>DRS = 100 × (P + O) / 2</strong><small>{t('当前每任务一个目标事件；P 与 O 各占 50%。','One target event per task in the current release; P and O each receive 50% weight.')}</small></div>
<p>{t('不适用的过程组件不进入均值，未满足的义务计零。后续修复可以提高结果分，但不会抹去已发生的禁止行为。参与者主动结束而未到达目标事件时，该事件记零；基础设施或构造失败单独排除。','Inapplicable process components are omitted; unmet requirements score zero. Later repairs can improve outcome credit but do not erase forbidden actions. Participant-controlled termination before the target event scores zero; infrastructure or construction failures are excluded separately.')}</p></section>
<section class="section"><h2>{t('统计与配对','Aggregation and pairing')}</h2><div class="two-col"><article class="panel"><h3>{t('任务成功率 S','Task success S')}</h3><p>{t('最终产物与执行证据满足所有任务目标的运行比例；分别报告 Batched 与 Async。S 不参与 DRS 的加权。','The percentage of runs whose final artifacts and execution evidence satisfy all task goals, reported for Batched and Async separately. S is not blended into DRS.')}</p></article><article class="panel"><h3>{t('八场景等权','Equal scenario weights')}</h3><p>{t('每次重复先对场景内 25 个任务求均值，再报告三次重复均值的平均值与样本标准差。总体 DRS 对八个场景等权平均。','For each repetition, average the 25 tasks in a scenario. Report the mean and sample SD of the three repetition-level means. Overall DRS weights all eight scenarios equally.')}</p></article></div><p>{t('所有 200 个任务 × 九个模型 × 两种交付模式 × 三次重复 = 10,800 次主实验运行。模式间按任务和重复编号配对；环境、任务、验证器版本、模型配置及资源限制保持匹配。','All 200 tasks × nine agents × two delivery modes × three repetitions = 10,800 main-experiment runs. Modes are paired by task and repetition with matched environments, task/verifier versions, model configurations and limits.')}</p></section>
<section class="section"><h2>{t('运行限制','Runtime limits')}</h2><div class="table-wrap"><table><tbody>
<tr><th>{t('主代理响应上限','Main-agent response horizon')}</th><td>100</td></tr><tr><th>{t('每次子代理执行响应上限','Responses per subagent execution')}</th><td>40</td></tr><tr><th>{t('每次响应输出 token 上限','Output token cap per response')}</th><td>16,384</td></tr><tr><th>{t('并发子代理限制','Subagent concurrency limit')}</th><td>3</td></tr><tr><th>{t('运行时间上限','Episode time limit')}</th><td>2,400 s</td></tr><tr><th>{t('紧急 token 保险丝','Emergency token fuse')}</th><td>5,000,000 · {t('非计分资源安全退出','unscored resource-safety abort')}</td></tr></tbody></table></div><p class="fine">{t('基准提供的初始工作流使用独立有界容量。详细约束以冻结的配置和协议为准；常规步数耗尽仍计分，紧急资源退出不混作任务失败。','The current implementation gives benchmark-owned initial workflows separate bounded capacity. See the frozen configuration and protocol for details: normal step exhaustion remains scored; emergency resource aborts are not task failures.')}</p></section>
<section class="section" id="sources"><h2>{t('数据来源','Sources')}</h2><p>{t('榜单转录自 2026-09-26 提供的论文稿件：表 3（第 7 页）、表 4（第 9 页），验证与重建图来自图 3 和图 6。这些是论文报告值，不代表新实验或独立复现。','The leaderboard is transcribed from the manuscript supplied on 2026-09-26: Table 3 (page 7), Table 4 (page 9), with validation and rebuilding from Figures 3 and 6. These are paper-reported values, not new experiments or an independent reproduction.')}</p>
<p>{t('网页下载数据使用 DRS 0–100、成功率百分比与 ΔS 百分点。框架内部的得分字段使用 [0,1]，不可直接混用。差值按论文保留，不从已舍入的显示值重新计算。','Website downloads use DRS on 0–100, task success in percent and ΔS in percentage points. Framework score fields use [0,1]; do not mix these scales. Differences are preserved from the paper, not recomputed from rounded display values.')}</p>
<p>{t('任务目录由当前公开注册表和发布清单自动生成；逐任务事件标签、解答、隐藏测试与判分真值均不发布。旧实验诊断值不合并进论文榜单；历史版本仍可在 Git 提交记录中追溯。','The catalog is generated from the current public registry and release manifest. Per-task event labels, solutions, hidden tests and scoring truth are not published. Old diagnostic values are not merged into the paper table; historical versions remain in Git history.')}</p>
<div class="actions"><a class="button" href="{base}/data/leaderboard.json" download>{t('下载论文报告值及来源','Download reported values & provenance')}</a><a class="button" href="{REPO}/blob/main/paper_artifacts/experiment_manifest.json">{t('实验清单','Experiment manifest')}</a></div></section>
<section class="section"><h2>{t('文档与引用','Documentation & citation')}</h2><ul class="resource-list"><li><a href="{REPO}/blob/main/docs/protocol.md">{t('评测协议','Evaluation protocol')}</a></li><li><a href="{REPO}/blob/main/docs/adapter-protocol.md">{t('适配器协议','Adapter protocol')}</a></li><li><a href="{REPO}/blob/main/docs/dataset.md">{t('数据集与历史标签','Dataset & legacy labels')}</a></li><li><a href="{REPO}/blob/main/CITATION.cff">{t('引用信息','Citation metadata')}</a></li><li><a href="{REPO}/blob/main/THIRD_PARTY_LICENSES.md">{t('任务材料来源许可','Task-material licenses')}</a></li></ul><p class="fine">{t('代码与文档使用 Apache-2.0；转换后的任务材料遵循对应上游条款。作者信息在双盲审稿期间保持匿名。','Code and documentation use Apache-2.0; transformed task materials retain upstream terms. Author information remains anonymized during double-blind review.')}</p></section>'''


def render_pages(base, corpus, paper):
    payload = json.dumps({"paper": paper, "tasks": corpus['tasks']}, ensure_ascii=False).replace('<', '\\u003c')
    data = f'<script id="site-data" type="application/json">{payload}</script>'
    routes = {
        "": ("Overview", home(base,corpus,paper)), "tasks/": ("Tasks", task_page(base,corpus)),
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
