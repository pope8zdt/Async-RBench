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
    return f'<pre><code>{escape(text)}</code></pre>'


def document(base, route, title, body):
    nav = [("", "首页", "Overview"), ("tasks/", "任务", "Tasks"), ("leaderboard/", "榜单", "Results"), ("evaluate/", "运行", "Run"), ("docs/", "协议", "Protocol")]
    links = ''.join(f'<a href="{base}/{path}" {"aria-current=page" if route == path else ""}>{t(zh,en)}</a>' for path, zh, en in nav)
    return f'''<!doctype html>
<html lang="zh" data-theme="light"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="description" content="Async-RBench: 200 tasks for asynchronous task execution in LLM agents. Paper results, public tasks and reproducible evaluation protocol.">
<meta name="color-scheme" content="light dark"><title>{escape(title)} · Async-RBench</title>
<link rel="stylesheet" href="{base}/assets/site.css">
<script>try{{const p=JSON.parse(localStorage.getItem('async-rbench-paper-preferences')||'{{}}');document.documentElement.lang=p.language==='en'?'en':'zh';document.documentElement.dataset.theme=p.theme==='dark'||(!p.theme&&matchMedia('(prefers-color-scheme: dark)').matches)?'dark':'light'}}catch{{}}</script>
<script type="module" src="{base}/assets/site.mjs"></script></head>
<body data-base="{base}"><a class="skip-link" href="#main">{t('跳转到内容','Skip to content')}</a>
<header class="site-header"><div class="header-inner"><a class="brand" href="{base}/"><span class="brand-mark" aria-hidden="true">a↗</span>Async-RBench</a>
<nav aria-label="Main navigation">{links}</nav><div class="preferences" hidden data-enhance>
<button id="language" type="button">English</button><button id="theme" type="button">{t('深色','Dark')}</button></div></div></header>
<main id="main" tabindex="-1">{body}</main>
<footer><a class="brand" href="{base}/">Async-RBench</a><span>{t('200 个任务 · v11.0-paper','200 tasks · v11.0-paper')}</span>
<a href="{REPO}">GitHub ↗</a><a href="{base}/docs/#sources">{t('数据与说明','Sources & scope')}</a></footer>
<noscript><p class="noscript">页面内容无需 JavaScript 即可阅读。筛选、切换语言与主题需要启用 JavaScript。 / All content is readable without JavaScript. Enable it for filters, language and theme controls.</p></noscript>
</body></html>'''


def figure(base, name, zh, en):
    return f'<figure><a href="{base}/assets/{name}" aria-label="{escape(en)}"><img src="{base}/assets/{name}" alt="{escape(en)}" loading="lazy"></a><figcaption>{t(zh,en)}</figcaption></figure>'


def heading(label, zh, en, lead_zh, lead_en):
    return f'<section class="page-heading"><p class="eyebrow">{escape(label)}</p><h1>{t(zh,en)}</h1><p class="lead">{t(lead_zh,lead_en)}</p></section>'


def source_note(base):
    return f'<p class="source-note">{t("论文报告结果 · 2026-09-26 稿件 · 非网站实时测评或独立复现。", "Paper-reported results · manuscript snapshot 2026-09-26 · not live evaluations or independent reproductions.")} <a href="{base}/docs/#sources">{t("来源与统计口径", "Source & aggregation")}</a></p>'


def result_rows(base, paper):
    rows = []
    for rank, record in enumerate(sorted(paper["records"], key=lambda r: -r["drs"]), 1):
        rows.append(f'''<tr data-record="{record['id']}"><td class="rank">{rank:02}</td><th scope="row"><a href="{base}/runs/{record['id']}/">{escape(record['model'])} <span class="arrow">↗</span></a></th>
<td class="drs-cell"><span class="score-bar" style="--score:{record['drs']}%"></span><strong>{record['drs']:.1f}</strong></td>
<td>{record['batched']:.1f}</td><td>{record['async']:.1f}</td><td class="delta">{record['delta']:+.1f}</td><td>{record['calls']:.1f}</td></tr>''')
    return ''.join(rows)


def leaderboard(base, paper, compact=False):
    controls = '' if compact else f'''<div class="filters" data-enhance hidden><label>{t('搜索模型','Search models')}<input id="model-search" type="search" autocomplete="off"></label>
<label>{t('排序指标','Rank by')}<select id="metric"><option value="drs">DRS ↓</option><option value="async">Async S ↓</option><option value="batched">Batched S ↓</option><option value="delta">ΔS ↓</option></select></label>
<a class="button subtle" href="{base}/data/leaderboard.json" download>JSON ↓</a><a class="button subtle" href="{base}/data/leaderboard.csv" download>CSV ↓</a></div>'''
    mean = paper['mean']
    return f'''{controls}<div class="table-wrap" tabindex="0" role="region" aria-label="Paper results table"><table class="results-table">
<caption class="sr-only">{t('论文九模型结果；DRS 为 0–100，S 为百分比，ΔS 为百分点。','Nine paper agents: DRS on 0–100, S in percent, ΔS in percentage points.')}</caption>
<thead><tr><th>{t('排名','Rank')}</th><th>{t('模型','Model')}</th><th>DRS ↑</th><th>Batched S ↑</th><th>Async S ↑</th><th>ΔS ↑</th><th>{t('调用次数','Calls')}</th></tr></thead>
<tbody id="result-rows">{result_rows(base,paper)}</tbody><tfoot><tr><td></td><th>{t('九模型均值','Mean, nine agents')}</th><td>{mean['drs']:.1f}</td><td>{mean['batched']:.1f}</td><td>{mean['async']:.1f}</td><td>{mean['delta']:+.1f}</td><td>{mean['calls']:.1f}</td></tr></tfoot></table></div>
<p id="result-empty" class="empty-state" hidden>{t('没有匹配的模型。请尝试其他关键词。','No matching models. Try another search.')}</p>
<p class="fine">{t('ΔS = Async − Batched，单位为百分点；保留论文按未舍入数据计算的差值。调用次数为每次 Async 运行中主代理与全部子代理的平均响应总数。', 'ΔS = Async − Batched, in percentage points; differences retain the paper’s pre-rounding calculations. Calls counts mean main-agent and all subagent responses per Async run.')}</p>{source_note(base)}'''


def home(base, corpus, paper):
    stats = ''.join(f'<div><strong>{n}</strong><span>{t(zh,en)}</span></div>' for n, zh, en in [(str(corpus['task_count']), '评测任务','evaluation tasks'), ('8','异步场景','async scenarios'), ('9','评测模型','evaluated agents'), ('10,800','主实验运行','main-experiment runs')])
    return f'''<section class="hero"><p class="eyebrow"><span class="dot"></span> ASYNC-RBENCH · v11.0</p><h1>Async-RBench</h1>
<p class="hero-subtitle">Benchmarking Asynchronous Task Execution<br class="desktop-break"> in LLM Agents</p>
<p class="lead">{t('结果陆续到达，任务仍在继续。代理能否修正受影响的工作、保留有效进展，并重新验证？','Results arrive while work continues. Can an agent revise what changed, preserve valid progress, and verify again?')}</p>
<div class="actions"><a class="button primary" href="{base}/leaderboard/">{t('查看论文结果','Explore paper results')} ↗</a><a class="button" href="{REPO}">{t('代码与任务集','Code & dataset')} ↗</a><a class="text-link" href="{base}/evaluate/">{t('运行测评','Run the benchmark')} →</a></div></section>
<section class="stats" aria-label="Benchmark statistics">{stats}</section>
{figure(base,'overview.png','论文图 1 · 异步执行中的结果整合与重规划。','Paper Figure 1 · Result integration and replanning during asynchronous execution.')}
<section class="section"><div class="section-title"><div><p class="eyebrow">THE QUESTION</p><h2>{t('完成任务，不等于正确处理新结果。','Task completion is not the whole story.')}</h2></div></div>
<div class="two-col"><article class="panel"><span class="tag">BATCHED</span><h3>{t('并行执行，集中交付','Concurrent work, batched delivery')}</h3><p>{t('子代理并行工作。所有必需工作流结束后，结果一次性交给主代理。','Subagents run concurrently. Results are presented together after all required workflows terminate.')}</p></article>
<article class="panel tinted"><span class="tag">ASYNC</span><h3>{t('主线继续，结果逐个交付','Work continues, results arrive incrementally')}</h3><p>{t('主代理继续执行；场景控制器在约定任务状态下逐个交付合格结果，代理自行判断如何响应。','The main agent continues working. A scenario controller presents eligible results at predefined task-state boundaries; the agent decides how to respond.')}</p></article></div>
<p class="fine">{t('两种模式使用相同任务、工作流和资源限制，但分别执行子代理，因此生成结果和后续路径可能不同。','Both modes use the same tasks, workflows and limits, but execute subagents independently, so generated results and later actions may differ.')}</p></section>
<section class="section"><div class="section-title"><div><p class="eyebrow">PAPER RESULTS</p><h2>{t('九个模型，同一评测协议。','Nine agents. One evaluation protocol.')}</h2></div><a class="text-link" href="{base}/leaderboard/">{t('完整结果与场景细分','Full results & scenarios')} ↗</a></div>{leaderboard(base,paper,True)}</section>
<section class="section"><div class="finding-grid"><article><span class="finding-number">19.2–45.1</span><h3>{t('异步重规划仍有明显不足','Substantial room for better replanning')}</h3><p>{t('九模型的 Async DRS 均低于 50。重复结果和子代理失败是平均得分最低的两个场景。','All nine Async DRS scores are below 50. Duplicate reports and subagent failures have the lowest mean scenario scores.')}</p></article>
<article><span class="finding-number">29.7% → 26.0%</span><h3>{t('异步交付下成功率下降','Lower task success under Async')}</h3><p>{t('在论文协议下，九模型的任务成功率点估计均下降；这里不将该现象推广为所有异步系统的因果结论。','Under the paper protocol, all nine agents have lower task-success point estimates; this is not a causal claim about all asynchronous systems.')}</p></article>
<article><span class="finding-number">+2.6–3.5</span><h3>{t('强制重建计划带来有限提升','Full rebuilding yields limited gains')}</h3><p>{t('三个模型的 DRS 小幅提高；论文正文报告平均调用次数增加 7.5–10.2%，图文数值差异见结果页。','DRS improves modestly on three agents. The paper text reports 7.5–10.2% more calls; see the results page for a figure/text discrepancy.')}</p></article></div></section>
<section class="section"><div class="section-title"><h2>{t('协议、任务与复现','Protocol, tasks and reproduction')}</h2></div><div class="link-grid">
<a class="panel" href="{base}/tasks/"><h3>{t('200 个公开任务','200 public tasks')} ↗</h3><p>{t('查看来源、难度与初始子任务数。','Browse sources, difficulty and initial subtask counts.')}</p></a>
<a class="panel" href="{base}/docs/"><h3>{t('ERC 与 DRS','ERC & DRS')} ↗</h3><p>{t('了解过程与结果各占一半的判分。','Understand the equal process/outcome weighting.')}</p></a>
<a class="panel" href="{base}/evaluate/"><h3>{t('本地运行测评','Run locally')} ↗</h3><p>{t('公开框架、配置模板与独立 judge。','Public framework, model template and external judge.')}</p></a></div></section>'''


def task_page(base, corpus):
    cards = ''.join(f'<article class="scenario-card"><div><span class="scenario-index">{i:02}</span><span class="tag">25 {t("任务","tasks")}</span></div><h3>{t(zh,en)}</h3><p>{t(zd,ed)}</p></article>' for i, (_, zh,en,zd,ed) in enumerate(SCENARIOS,1))
    sources = ''.join(f'<div class="source-item"><span>{SOURCES[key]}</span><strong>{count}</strong></div>' for key,count in corpus['source_counts'].items())
    rows = ''.join(f'''<tr data-task="{escape(task['id'])}"><th scope="row"><a href="{task['url']}">{escape(task['title'])} ↗</a><code class="case-id">{escape(task['id'])}</code></th><td>{SOURCES[task['source']]}</td><td>{t('中等','Medium') if task['difficulty']=='medium' else t('困难','Hard')}</td><td>{task['subtasks']}</td></tr>''' for task in corpus['tasks'])
    options = ''.join(f'<option value="{key}">{value}</option>' for key,value in SOURCES.items())
    return heading('DATASET','200 个任务，八类异步场景。','200 tasks, eight async scenarios.','五个来源各 40 个任务；所有 200 个任务均进入论文主实验。','40 tasks from each of five sources; all 200 enter the paper’s main experiment.') + f'''
<div class="source-strip">{sources}</div><div class="mini-stats"><span><strong>621</strong> {t('初始子任务','initial subtasks')}</span><span><strong>104 / 96</strong> {t('中等 / 困难','medium / hard')}</span><span><strong>73 / 40 / 87</strong> {t('分别有 2 / 3 / ≥4 个子任务','with 2 / 3 / ≥4 subtasks')}</span></div>
<section class="section"><h2>{t('场景覆盖','Scenario coverage')}</h2><div class="scenario-grid">{cards}</div><p class="fine">{t('每个任务只按一个主场景计数。场景分布为总体统计；公开目录不披露逐任务私有事件标注。','Each task counts once under its primary scenario. These are aggregate counts; the public catalog does not expose private per-task event labels.')}</p></section>
<section class="section"><div class="section-title"><h2>{t('公开任务目录','Public task catalog')}</h2><a href="{base}/data/corpus.json" download class="text-link">JSON ↓</a></div>
<div class="filters" data-enhance hidden><label>{t('搜索标题或编号','Search title or ID')}<input type="search" id="task-search" autocomplete="off"></label><label>{t('来源','Source')}<select id="task-source"><option value="" data-zh="全部来源" data-en="All sources">全部来源</option>{options}</select></label><label>{t('难度','Difficulty')}<select id="task-difficulty"><option value="" data-zh="全部难度" data-en="All levels">全部难度</option><option value="medium" data-zh="中等" data-en="Medium">中等</option><option value="hard" data-zh="困难" data-en="Hard">困难</option></select></label><button class="button subtle" id="task-reset" type="button">{t('清除筛选','Reset filters')}</button></div>
<p class="fine" id="task-count" aria-live="polite">200 / 200 {t('任务','tasks')}</p><div class="table-wrap task-table" tabindex="0" role="region" aria-label="Public task catalog"><table><thead><tr><th>{t('任务与编号','Task / identifier')}</th><th>{t('来源','Source')}</th><th>{t('难度','Difficulty')}</th><th>{t('子任务数','Subtasks')}</th></tr></thead><tbody id="task-rows">{rows}</tbody></table></div><p class="empty-state" id="task-empty" hidden>{t('没有匹配的任务。请放宽筛选条件。','No matching tasks. Try less restrictive filters.')}</p></section>
<section class="panel"><h2>{t('公开边界与数据划分','Release boundary and legacy labels')}</h2><p>{t('论文另有 47 个独立构造任务，不包含在这个 200 任务发布集中。注册表中的 81/30/89 是历史诊断标签，不是论文的校准、开发和测试划分，也不证明任务从未参与开发。','The paper reports 47 separate construction tasks, outside this 200-task release. The registry’s 81/30/89 counts are legacy diagnostic labels, not the paper’s calibration/development/test partitions or proof of no development exposure.')}</p><p>{t('每个公开任务包含 public/、task/ 和 PROVENANCE.md。解答、隐藏测试、事件时序、验证器和实验轨迹不在公开包中。','Each public task contains public/, task/ and PROVENANCE.md. Solutions, hidden tests, event schedules, verifiers and experiment traces are excluded.')}</p><a href="{REPO}/blob/main/docs/dataset.md">{t('完整数据集说明','Full dataset guide')} ↗</a></section>'''


def results_page(base, paper):
    header = heading('PAPER RESULTS','论文结果','Paper results','九个主代理—子代理系统使用相同模型、工具接口与评测协议。','Nine main–subagent systems, with the same model in both roles and a shared tool interface and protocol.')
    return header + leaderboard(base,paper) + f'''<section class="section"><h2>{t('按场景查看','Compare by scenario')}</h2><p>{t('点击模型名称查看八场景的均值与样本标准差，每个场景基于三次重复实验。总体 DRS 对八场景等权平均；表中排名不代表统计显著性。','Open a model to inspect mean and sample SD across three repetitions in each scenario. Overall DRS weights the eight scenarios equally; rankings do not imply statistical significance.')}</p></section>
<section class="section"><h2>{t('DRS 验证与计划重建','DRS validation & plan rebuilding')}</h2><div class="two-col figure-grid"><article>{figure(base,'drs-validation.png','论文图 3 · 相同目标事件上的 Oracle / Native / Frozen。','Paper Figure 3 · Oracle / Native / Frozen on the same target events.')}<p>{t('Oracle 为知晓事件要求的参考恢复程序，不是能力匹配的基线。Frozen 使用同一模型在看不到目标结果时生成的后续动作。','Oracle is a reference recovery program with knowledge of event requirements, not a capability-matched baseline. Frozen uses a continuation generated by the same model without the target result.')}</p></article><article>{figure(base,'full-rebuild.png','论文图 6 · Full-rebuild 与 Native 的 DRS 和调用代价。','Paper Figure 6 · DRS and call costs under Full-rebuild and Native.')}<p>{t('Full-rebuild 在每次子代理结果交付后重建剩余计划，同时保留已完成工作。该三模型干预实验独立于主实验。','Full-rebuild reconstructs the remaining plan after each subagent result while retaining completed work. This three-agent intervention is separate from the main experiment.')}</p><p class="fine">{t('来源说明：图 6 直接取自提供的论文，Gemini Native 的子代理调用数为 55.5。图中调用数与正文报告的 7.5–10.2% 增幅不能完全对应；这里保留稿件原值，未重新计算或更改实验结果。','Source note: Figure 6 is rendered directly from the supplied manuscript, with 55.5 Gemini Native subagent calls. Its call counts do not fully reconcile with the text’s reported 7.5–10.2% increase. Both are preserved as reported; no experiment results have been recalculated or changed.')}</p></article></div></section>'''


def model_page(base, record):
    rows = ''.join(f'<tr><th scope="row">{t(zh,en)}</th><td>{record["scenarios"][key]["mean"]:.1f}</td><td>± {record["scenarios"][key]["sd"]:.1f}</td></tr>' for key,zh,en,*_ in SCENARIOS)
    return f'<a class="back-link" href="{base}/leaderboard/">← {t("返回论文结果","All paper results")}</a>' + heading('AGENT RESULTS', record['model'], record['model'], '论文表 3 / 表 4；不是单次运行记录。','Paper Tables 3 / 4; not an individual run trace.') + f'''
<div class="stats"><div><strong>{record['drs']:.1f}</strong><span>Async DRS</span></div><div><strong>{record['batched']:.1f}%</strong><span>Batched S</span></div><div><strong>{record['async']:.1f}%</strong><span>Async S</span></div><div><strong>{record['delta']:+.1f}</strong><span>ΔS · {t('百分点','pp')}</span></div></div>
<section class="section narrow"><h2>{t('场景 DRS','Scenario DRS')}</h2><div class="table-wrap"><table><thead><tr><th>{t('场景','Scenario')}</th><th>{t('均值','Mean')}</th><th>{t('样本标准差','Sample SD')}</th></tr></thead><tbody>{rows}</tbody></table></div><p class="fine">{t('每场景 25 个任务，每模式 3 次重复；每模型每模式 600 次运行。','25 tasks per scenario, three repetitions per mode; 600 runs per agent per mode.')} {t('平均 Async 调用次数：','Mean Async calls: ')}{record['calls']:.1f}.</p>{source_note(base)}</section>'''


def evaluate_page(base):
    setup = 'git clone https://github.com/pope8zdt/Async-RBench.git\ncd Async-RBench\npython -m venv .venv\n# Activate: .venv\\Scripts\\Activate.ps1 (PowerShell)\n# or: source .venv/bin/activate (bash)\npython -m pip install -e ".[test]"\nasync-rbench validate-public\nasync-rbench list\npython -m pytest -q'
    validate = 'async-rbench validate-judge --judge-root <judge-root>\nasync-rbench certify-release --judge-root <judge-root>'
    manifest = 'async-rbench-eval make-manifest --output manifest.json --repetitions 3 --guidance incentive --seed 2026 --execution-modes linear async --model <model-id> --judge-root <judge-root>'
    run = 'async-rbench-eval run-manifest --manifest manifest.json --output <run-directory> --profile reference_scaffold_api --runtime-mode api_only --config <profile.yaml> --official-track --judge-root <judge-root>'
    aggregate = 'async-rbench-eval aggregate --root <run-directory> --manifest manifest.json --output aggregate.json\nasync-rbench-eval audit-run --root <run-directory> --output audit.json'
    return heading('RUN LOCALLY','运行测评','Run the benchmark','网页提供公开资料与命令，不在浏览器中运行代理，也不收集 API 密钥。','This website provides public materials and commands. It does not run agents in your browser or collect API keys.') + f'''
<div class="notice">{t('公开任务可以直接检查；正式判分还需要匹配版本的外置 judge、Docker 和模型 API。下载仓库本身不包含 judge，也不能单独复现正式分数。','You can inspect public tasks immediately. Formal scoring also requires a matching external judge, Docker and a model API. The repository does not include the judge and cannot reproduce formal scores on its own.')}</div>
<section class="step"><span class="step-number">01</span><div><h2>{t('安装并检查公开任务','Install and validate public tasks')}</h2><p>Python 3.11+ · Git</p>{code(setup)}</div></section>
<section class="step"><span class="step-number">02</span><div><h2>{t('准备 judge 与模型配置','Prepare the judge and model profile')}</h2><p>{t('取得与 v11.0-paper 匹配的 judge bundle 后，在本地验证。网站不提供隐藏判分材料。','After obtaining the judge bundle matching v11.0-paper, validate it locally. Hidden scoring materials are not distributed on this website.')}</p>{code(validate)}
<p>{t('复制配置模板，在本地填写模型标识和服务地址；密钥只放在环境变量中。论文中主代理与子代理使用同一模型。','Copy the template and fill in model identifiers and your provider URL locally. Keep the key in an environment variable. The paper uses the same model for main and subagents.')}</p><a class="button" href="{base}/data/experiment-profile.template.yaml" download>{t('下载配置模板','Download profile template')} ↓</a><a class="text-link" href="{REPO}/tree/main/configs/model-profiles">{t('查看配置说明','Configuration reference')} ↗</a></div></section>
<section class="step"><span class="step-number">03</span><div><h2>{t('创建并运行配对计划','Create and run the paired manifest')}</h2><p>{t('替换尖括号占位值，不要把占位符原样运行。内部键 linear 表示 Batched，不是串行执行。每个模型的完整计划为 1,200 次运行；九模型合计 10,800 次。','Replace angle-bracket placeholders before running. The internal key linear means Batched, not serial execution. A full manifest contains 1,200 runs per agent; nine agents total 10,800.')}</p>{code(manifest)}{code(run)}<p class="fine">{t('这些命令会在你的机器上调用模型，可能产生 API 费用。formal 模式会检查隔离、资源配置与适配器合规。','These commands call models on your machine and may incur API costs. Official mode checks isolation, resource configuration and adapter conformance.')}</p></div></section>
<section class="step"><span class="step-number">04</span><div><h2>{t('汇总与审计','Aggregate and audit')}</h2>{code(aggregate)}<p>{t('保留版本、配置、覆盖率和排除原因；基础设施故障不能记为模型失败，缺失结果不能填零。','Retain versions, configurations, coverage and exclusion reasons. Infrastructure failures must not count as model failures; missing results must not be filled with zeros.')}</p><a href="{REPO}/blob/main/docs/cli.md">{t('完整命令行文档','Full CLI reference')} ↗</a></div></section>
<section class="panel"><h2>{t('结果提交','Sharing results')}</h2><p>{t('当前网站展示论文报告的固定结果，不提供在线任务队列、自动判分或自动上榜。新增结果应先与维护者确认协议和所需证据，不要在公开 Issue 或提交中上传密钥、隐藏 judge 或原始私有轨迹。','This website displays the paper’s fixed results. It has no online job queue, scoring backend or automatic ranking submissions. Discuss protocol and evidence requirements with maintainers before contributing results; never upload keys, hidden judges or private raw traces to public issues or submissions.')}</p><a href="{REPO}/issues">{t('联系维护者','Contact maintainers')} ↗</a></section>'''


def docs_page(base):
    obligations = ''.join(f'<article class="panel"><span class="obligation">{symbol}</span><h3>{t(zh,en)}</h3><p>{t(zd,ed)}</p></article>' for symbol,zh,en,zd,ed in [
        ('C','Change · 必要修改','Change','修改被新证据影响的产物或计划。','Revise artifacts or plans affected by new evidence.'),
        ('R','Preserve · 保留有效工作','Preserve','保留依然有效的状态和已完成工作。','Retain state and completed work that remain valid.'),
        ('F','Forbid · 避免禁止行为','Forbid','避免重复副作用、无关回退和其他禁止更改。','Avoid duplicate side effects, unrelated rollbacks and other forbidden changes.'),
        ('V','Verify · 重新验证','Verify','重跑受影响的检查，形成可核查的验证证据。','Repeat affected checks and produce verifiable evidence.')])
    return heading('PROTOCOL','测量响应，而不只看终点。','Measure the response, not just the endpoint.','任务成功率 S 与动态重规划分数 DRS 分开报告。','Task success S and Dynamic Replanning Score DRS are reported separately.') + f'''
{figure(base,'benchmark-mechanism.png','论文图 2 · 控制器、结果交付与 ERC 判分。','Paper Figure 2 · Controller, result presentation and ERC scoring.')}
<section class="section" id="scoring"><h2>{t('事件响应契约 ERC','Event Response Contract')}</h2><p>{t('每个目标事件都有私有 ERC，定义四类过程要求以及最终结果 O。契约限定应满足的义务，而不强制唯一动作序列。','Each target event has a private ERC defining four process requirements and final outcome O. It specifies obligations, not a unique action sequence.')}</p><div class="obligation-grid">{obligations}</div>
<div class="formula"><span>P = mean(applicable C, R, F, V)</span><strong>DRS = 100 × (P + O) / 2</strong><small>{t('当前每任务一个目标事件；P 与 O 各占 50%。','One target event per task in the current release; P and O each receive 50% weight.')}</small></div>
<p>{t('不适用的过程组件不进入均值，未满足的义务计零。后续修复可以提高结果分，但不会抹去已发生的禁止行为。参与者主动结束而未到达目标事件时，该事件记零；基础设施或构造失败单独排除。','Inapplicable process components are omitted; unmet requirements score zero. Later repairs can improve outcome credit but do not erase forbidden actions. Participant-controlled termination before the target event scores zero; infrastructure or construction failures are excluded separately.')}</p></section>
<section class="section"><h2>{t('聚合与配对协议','Aggregation and pairing')}</h2><div class="two-col"><article class="panel"><h3>{t('任务成功率 S','Task success S')}</h3><p>{t('最终产物与执行证据满足所有任务目标的运行比例；分别报告 Batched 与 Async。S 不参与 DRS 的加权。','The percentage of runs whose final artifacts and execution evidence satisfy all task goals, reported for Batched and Async separately. S is not blended into DRS.')}</p></article><article class="panel"><h3>{t('八场景等权','Equal scenario weights')}</h3><p>{t('每次重复先对场景内 25 个任务求均值，再报告三次重复均值的平均值与样本标准差。总体 DRS 对八个场景等权平均。','For each repetition, average the 25 tasks in a scenario. Report the mean and sample SD of the three repetition-level means. Overall DRS weights all eight scenarios equally.')}</p></article></div><p>{t('所有 200 个任务 × 九个模型 × 两种交付模式 × 三次重复 = 10,800 次主实验运行。模式间按任务和重复编号配对；环境、任务、验证器版本、模型配置及资源限制保持匹配。','All 200 tasks × nine agents × two delivery modes × three repetitions = 10,800 main-experiment runs. Modes are paired by task and repetition with matched environments, task/verifier versions, model configurations and limits.')}</p></section>
<section class="section"><h2>{t('资源与终止条件','Resource and termination contract')}</h2><div class="table-wrap"><table><tbody>
<tr><th>{t('主代理响应上限','Main-agent response horizon')}</th><td>100</td></tr><tr><th>{t('每次子代理执行响应上限','Responses per subagent execution')}</th><td>40</td></tr><tr><th>{t('每次响应输出 token 上限','Output token cap per response')}</th><td>16,384</td></tr><tr><th>{t('并发子代理限制','Subagent concurrency limit')}</th><td>3</td></tr><tr><th>{t('运行时间上限','Episode time limit')}</th><td>2,400 s</td></tr><tr><th>{t('紧急 token 保险丝','Emergency token fuse')}</th><td>5,000,000 · {t('非计分资源安全退出','unscored resource-safety abort')}</td></tr></tbody></table></div><p class="fine">{t('当前实现对 benchmark-owned 初始工作流使用独立有界容量。详细约束以冻结的配置和协议为准；常规步数耗尽仍计分，紧急资源退出不混作任务失败。','The current implementation gives benchmark-owned initial workflows separate bounded capacity. See the frozen configuration and protocol for details: normal step exhaustion remains scored; emergency resource aborts are not task failures.')}</p></section>
<section class="section" id="sources"><h2>{t('数据来源与可验证边界','Sources and evidence boundary')}</h2><p>{t('榜单转录自 2026-09-26 提供的论文稿件：表 3（第 7 页）、表 4（第 9 页），验证与重建图来自图 3 和图 6。这里只发布报告值，不声称网站重新运行实验或完成独立复现。','The leaderboard is transcribed from the manuscript supplied on 2026-09-26: Table 3 (page 7), Table 4 (page 9), with validation and rebuilding from Figures 3 and 6. These are reported values, not new executions or independent reproductions by the website.')}</p>
<p>{t('网页下载数据使用 DRS 0–100、成功率百分比与 ΔS 百分点。框架内部的得分字段使用 [0,1]，不可直接混用。差值按论文保留，不从已舍入的显示值重新计算。','Website downloads use DRS on 0–100, task success in percent and ΔS in percentage points. Framework score fields use [0,1]; do not mix these scales. Differences are preserved from the paper, not recomputed from rounded display values.')}</p>
<p>{t('任务目录由当前公开注册表和发布清单自动生成；逐任务事件标签、解答、隐藏测试与判分真值均不发布。旧实验诊断值不合并进论文榜单；历史版本仍可在 Git 提交记录中追溯。','The catalog is generated from the current public registry and release manifest. Per-task event labels, solutions, hidden tests and scoring truth are not published. Old diagnostic values are not merged into the paper table; historical versions remain in Git history.')}</p>
<div class="actions"><a class="button" href="{base}/data/leaderboard.json" download>{t('下载论文报告值及来源','Download reported values & provenance')} ↓</a><a class="button" href="{REPO}/blob/main/paper_artifacts/experiment_manifest.json">{t('实验清单','Experiment manifest')} ↗</a></div></section>
<section class="section"><h2>{t('文档与引用','Documentation & citation')}</h2><ul class="resource-list"><li><a href="{REPO}/blob/main/docs/protocol.md">{t('评测协议','Evaluation protocol')} ↗</a></li><li><a href="{REPO}/blob/main/docs/adapter-protocol.md">{t('适配器协议','Adapter protocol')} ↗</a></li><li><a href="{REPO}/blob/main/docs/dataset.md">{t('数据集与历史标签','Dataset & legacy labels')} ↗</a></li><li><a href="{REPO}/blob/main/CITATION.cff">{t('引用信息','Citation metadata')} ↗</a></li><li><a href="{REPO}/blob/main/THIRD_PARTY_LICENSES.md">{t('任务材料来源许可','Task-material licenses')} ↗</a></li></ul><p class="fine">{t('代码与文档使用 Apache-2.0；转换后的任务材料遵循对应上游条款。作者信息在双盲审稿期间保持匿名。','Code and documentation use Apache-2.0; transformed task materials retain upstream terms. Author information remains anonymized during double-blind review.')}</p></section>'''


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
    archived = heading('ARCHIVED LINK','旧实验记录未并入论文榜单','Historical record not in the paper table','这个地址属于早期网站记录，或页面不存在。请查看当前论文结果；旧数据仍保留在仓库历史中。','This address belongs to an earlier record or a missing page. View the current paper results; historical data remains in repository history.')
    archived += f'<div class="actions"><a class="button primary" href="{base}/leaderboard/">{t("查看论文结果","Current paper results")} →</a><a class="button" href="{REPO}/tree/19e21e50fbea45812a3d845e1ade8c3a842ca9a9/website">{t("查看历史网站源码","Historical website source")} ↗</a></div>'
    pages['404.html'] = document(base,'','Page not found',archived)
    # Keep old published result links useful without relabeling them as paper runs.
    for old_id in ('e87590fa970dc29a','c484afc989d4a191','dfbf12394889e1f1','e4c241be482abb98'):
        pages[f'runs/{old_id}/index.html'] = document(base,'','Historical record',archived)
    return pages
