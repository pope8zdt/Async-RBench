# Agent Benchmark 实验设计调研与 DTBench 优化审计

> 调研截止：2026-08-30  
> 研究对象：近几年 Agent、Tool-use、GUI/Web、软件工程、长程任务、多 Agent/编排 Benchmark 及少量直接相关的分析论文。  
> 目的：不按“谁的总分更高”罗列论文，而是抽取每篇论文如何用实验支撑其核心研究主张，并据此审计 DTBench（仓库中也称 Async-RBench）的实验链条。

## 1. 结论先行

当前 DTBench 的研究动机是清楚且有辨识度的：**当长程 Agent 从顺序工具调用走向并发 subagent 委派后，主 Agent 是否能在异步结果回流、部分完成、权威更新、冲突、陈旧结果、失败和资源变化下持续维护并修正计划。** 现有主方案的同实例 `Linear vs Async`、私有事件真值、语义结果与动态控制双层评分、case-specific causal decision group，都比只看最终任务成功率的常见 benchmark 更接近这一构念。

调研后的核心判断不是“再堆更多基线”，而是做五项收束和增强：

1. **把论文证据链重排为七个连续问题**：构念有效性 → 异步是否造成因果退化 → 哪类事件造成退化 → 失败发生在控制闭环哪一阶段 → 瓶颈在主 Agent、worker、时序还是资源 → 不同控制策略如何权衡质量/时间/浪费 → 结论是否可靠且可迁移。
2. **增加 frozen event tape（冻结事件带）诊断轨道**：给不同 controller 回放相同 worker payload、完成时序和事件内容，隔离 controller 能力与 worker 随机性；再在 source-native 端到端环境的代表性子集验证外部效度。
3. **用阶段漏斗取代只有总分的能力解释**：事件摄取 → 状态/权威修正 → 受影响集识别 → 计划动作 → closure/reverification。每一步只在真实机会集上报告条件通过率。
4. **把条件化诊断变成严格单变量反事实**：`perfect-worker` 只替换 payload 正确性；`dependency oracle` 只在事件到达时公开受影响 closure；`canonical-order` 只改变到达顺序；资源诊断优先采用 `instant-return/fixed virtual time`，而不是笼统 resource relaxation。
5. **将 benchmark 有效性证据前置**：human/oracle ceiling、verifier 与人工一致性、等价解接受率、mutation kill rate、事件机会覆盖、基础设施有效率。否则主结果再大，也可能被解释为 verifier 或 case 构造效应。

建议保留 `实验设计.md` 当前框架，但把主文实验收束为“3 个核心表 + 4 个核心图”，其余放附录。`Model-Native / Greedy / Wait-All / Version-Aware / Oracle` 仍有价值，但应属于控制策略实验，不应与 benchmark 组件消融混为一谈。

---

## 2. 调研方法与纳入标准

### 2.1 纳入标准

- 2023–2026 年为主，少量经典工作用于建立实验范式；
- 论文研究对象至少涉及长程 Agent、交互环境、工具调用、多 Agent协作、动态状态、真实软件任务或 agent 可靠性；
- 优先读取论文原文 HTML/PDF、正式会议页面和官方项目页；
- 抽取重点不是 benchmark 介绍，而是：主实验、比较对象、控制变量、诊断/消融、统计设计、最能支撑论文意义的结果；
- 对未正式发表的新工作明确标注为 arXiv/preprint，不把“新”误当成“权威”。

### 2.2 文献分组

本报告纳入 **46 篇核心 benchmark/评测论文**，另列 4 篇与动态编排直接相关的系统或失效分析论文作为补充证据。它们分为：

- 通用、Web、GUI 与真实工作环境：13 篇；
- Tool-use、状态交互与安全：11 篇；
- 软件工程、科学任务与超长程 Agent：14 篇；
- 多 Agent、协作与编排：8 篇；
- 补充的多 Agent 系统/失效研究：4 篇。

---

## 3. 46 篇论文的实验设计证据矩阵

### 3.1 通用、Web、GUI 与真实工作环境

| # | 论文 | 主实验与比较 | 最重要的分析设计 | 对 DTBench 的直接启示 |
|---:|---|---|---|---|
| 1 | [AgentBench](https://arxiv.org/abs/2308.03688)（ICLR 2024） | 8 个交互环境、29 个闭源/开源模型；统一 Agent 协议比较跨环境成功率 | 分解 timeout、上下文溢出、格式错误、无效动作等失败；比较代码训练、对齐与规模 | 不只给 aggregate score；应把基础设施失败、协议失败、控制决策失败严格分账 |
| 2 | [GAIA](https://arxiv.org/abs/2311.12983)（ICLR 2024） | 466 个真实问题，按 3 个难度等级比较人类与模型/助手 | 私有答案、人工可解性与难度分层；人类—模型差距形成 ceiling | 增加小规模 human/operator ceiling，证明任务难而不是 evaluator 怪异 |
| 3 | [AgentBoard](https://arxiv.org/abs/2401.13178)（2024） | 多环境统一比较 agent；除最终成功率外引入 progress rate | 用子目标完成度解释长程失败，并验证自动指标与人工判断的相关性 | DTBench 应画控制闭环的阶段漏斗与事件对齐恢复曲线，而非只报 D 分数 |
| 4 | [WebArena](https://arxiv.org/abs/2307.13854)（ICLR 2024） | 自托管真实网站，比较多种 LLM/web agent 与人类 | CoT 消融、不可行任务提示、模板一致性、任务类型与错误分析 | 主任务结果后需要受控 prompt/信息条件，检验是否因提示形式而非异步能力 |
| 5 | [VisualWebArena](https://arxiv.org/abs/2401.13649)（2024） | 视觉网页任务；文本观测、截图、多模态模型和 agent 配置对比 | 截图/可访问树/Set-of-Marks 等观测消融，按站点与任务类型切片 | 对事件通知/结果契约可做等价表示扰动，检验 controller 是否靠表面格式 |
| 6 | [WorkArena](https://arxiv.org/abs/2403.07718)（2024） | 33 类企业知识工作任务，比较开源/闭源 web agent | 按任务类型、步骤与失败原因分析；真实企业应用状态验证 | 语义 validator 必须检查最终状态与 collateral effects，不只看最终文本 |
| 7 | [WorkArena++](https://arxiv.org/abs/2407.05291)（2024） | 682 个组合式知识工作任务，强调跨页面和长程依赖 | 原子任务与组合任务对照、难度与长度分析 | 依赖深度和跨 workstream fan-out 应成为预注册结构切片 |
| 8 | [BrowserGym Ecosystem](https://arxiv.org/abs/2412.05467)（2025） | 在统一 scaffold 下跨多个 web benchmark 比较 6 类 LLM/agent 配置 | 统一 action/observation 后比较 agent 组件；跨 benchmark 排名稳定性 | 固定 scaffold 是主比较前提；跨 source benchmark 报告排名与效应异质性 |
| 9 | [OSWorld](https://arxiv.org/abs/2404.07972)（NeurIPS 2024） | 真实桌面环境，对多种多模态 agent 与人类比较 | screenshot/a11y/SoM 观测消融；分应用/跨应用；历史、分辨率、噪声、人工用时 | DTBench 应有信息通道消融、human time 和失败阶段分析；不要把观测缺失当重规划失败 |
| 10 | [AndroidWorld](https://arxiv.org/abs/2405.14573)（ICLR 2025） | 参数化 Android 任务；多种模型与 agent 对比 | 固定参数重复 20 次与变化参数重复 20 次；跨 Android 版本和 prompt | 把模型采样方差与 schedule/instance 方差分开，而不是只报 3 次总均值 |
| 11 | [AppWorld](https://aclanthology.org/2024.acl-long.850/)（ACL 2024） | 750 个跨 9 个应用、457 个 API 的组合任务；多模型/agent 基线 | 用 state-based unit tests 同时检查目标状态和 collateral damage；normal/challenge split | DTBench 的语义 S 与控制 D 分离是正确方向；应突出“结果正确但过程不安全/陈旧”的四象限 |
| 12 | [AssistantBench](https://aclanthology.org/2024.emnlp-main.505/)（EMNLP 2024） | 214 个现实网页助手任务；closed-book、RAG、web agents、专用 agent 与 ensemble | 同时报准确率、answer rate、precision；按任务与失败类型分析 | 除 pass rate 外报告 coverage/abstention；避免 agent 通过不作答规避动态错误 |
| 13 | [CRAB](https://aclanthology.org/2025.findings-acl.1113/)（Findings of ACL 2025） | 120 个桌面/移动任务；6 个模型；single-agent 与 multi-agent 配置 | graph evaluator 提供细粒度步骤进度，分析不同平台/任务/配置 | 用因果 decision-group DAG 做 progress 诊断，而非把每个日志事件都当同权检查点 |

### 3.2 Tool-use、状态交互与安全

| # | 论文 | 主实验与比较 | 最重要的分析设计 | 对 DTBench 的直接启示 |
|---:|---|---|---|---|
| 14 | [API-Bank](https://aclanthology.org/2023.emnlp-main.187/)（EMNLP 2023） | 73 个 API、314 段对话、753 次调用；比较多模型与 Lynx | 将能力拆为 API 检索、规划、调用和响应；逐阶段错误分析 | DTBench 阶段漏斗应把事件理解、计划更新和执行闭环分开评分 |
| 15 | [ToolLLM / ToolBench](https://arxiv.org/abs/2307.16789)（ICLR 2024） | 约 16K API；多种模型、检索器与 DFS 推理策略；in/out-domain | 检索与规划组件比较、不同工具类别/难度、自动 ToolEval | controller 对比必须固定可用工具、worker pool 和协议，否则无法归因 |
| 16 | [Berkeley Function-Calling Leaderboard](https://proceedings.mlr.press/v267/patil25a.html)（ICML 2025） | 广泛模型的 serial/parallel function calls、AST 及 multi-turn 状态评测 | 并行调用、拒答、状态保持、可执行性分开；细粒度错误类别 | 并发“能发出调用”与“能整合异步结果”是不同能力，论文需明确区分 |
| 17 | [ToolSandbox](https://arxiv.org/abs/2408.04682)（2024） | 多工具多轮状态任务；模型/agent 基线 | milestone DAG + minefield；工具/schema 扰动；状态依赖、信息不足、canonicalization、backtracking | 为 stale/duplicate/conflict 建立 must-do 与 must-not-do；增加事件契约等价扰动 |
| 18 | [τ-bench](https://arxiv.org/abs/2406.12045)（2024） | 用户模拟器 + 工具 + policy；function-calling、ReAct、Act 与多模型 | `pass^k` 可靠性；移除 policy；按 write 次数、成本和人工失败类型 | 同一 case 多次成功的稳定性比平均分更符合长程控制，至少报 pass²/pass³ |
| 19 | [τ²-bench](https://arxiv.org/html/2506.07982)（2025） | 多模型、4 次运行；Default、No-User、Oracle Plan 等条件 | 任务复杂度、policy 表示、用户模拟器可靠性；单变量信息/计划 oracle | Oracle 条件应只注入一种信息；反事实诊断必须写明它消除了哪条因果路径 |
| 20 | [AgentDojo](https://arxiv.org/abs/2406.13352)（NeurIPS 2024 Datasets & Benchmarks） | 在工具调用任务中系统评估 prompt injection 攻击和防御 | benign utility、受攻击 utility、targeted ASR；adaptive/union attack | 动态控制要同时报告任务效用和错误动作/过度反应，尤其 irrelevant event 的 false positive |
| 21 | [ST-WebAgentBench](https://arxiv.org/abs/2410.06703)（ICLR 2026） | 任务完成与策略合规联合评测，多种模型/agent | completion 与 policy compliance 正交；风险等级与违规类型 | S 与 D 不应过早合成一个数；“成功但控制违规”应成为 headline quadrant |
| 22 | [MCP-Bench](https://arxiv.org/abs/2508.20453)（2025） | 28 个真实 MCP server、250 个工具、20 个 LLM | 工具/schema 理解、trajectory planning、task completion 分层 | Structured result contract 更适合作为输入表示鲁棒性诊断，不是通用 Manager 组件消融 |
| 23 | [MCP-Universe](https://arxiv.org/abs/2508.14704)（2025） | 6 个领域、11 个真实 MCP server；模型与 scaffold 对比 | static/format/realtime evaluator 组合；跨 server 和 scaffold | 将静态检查、事件格式、实时状态和最终语义证据分开验证 |
| 24 | [Toolathlon](https://arxiv.org/abs/2510.25726)（ICLR 2026） | 108 个长程任务、32 个应用、604 个工具；多模型基线 | 可执行参考脚本；pass@1/pass@3/pass³、turns；真实工具组合 | 同时报告 capability、可靠性与效率；为每个 case 保留可执行 oracle/参考行为 |

### 3.3 软件工程、科学任务与超长程 Agent

| # | 论文 | 主实验与比较 | 最重要的分析设计 | 对 DTBench 的直接启示 |
|---:|---|---|---|---|
| 25 | [SWE-bench](https://arxiv.org/abs/2310.06770)（ICLR 2024） | 真实 GitHub issue；模型与 retrieval/context 配置比较 | BM25 vs oracle retrieval、context 长度/压缩、repo/日期/patch 复杂度 | source-native 任务应固定版本和 harness，并区分定位、修改与验证瓶颈 |
| 26 | [SWE-bench Multimodal](https://arxiv.org/abs/2410.03859)（ICLR 2025） | 517 个带视觉证据的 JS issue；文本与多模态 agent 比较 | 图像是否提供、模型/agent 配置、任务类别和失败样例 | 对异步结果中的 artifact 类型/观测通道做切片，但不可与时序处理混成同一因素 |
| 27 | [SWE-Lancer](https://proceedings.mlr.press/v267/miserendino25a.html)（ICML 2025） | 1400+ 个真实自由职业软件任务；独立 coding 与 managerial choice | 三重专家验证；按任务金额/类型/难度；管理决策和实际实现分开 | 管理/调度能力可以独立测，但仍需端到端任务验证；应同时给 controller-only 与 E2E 结果 |
| 28 | [Terminal-Bench 2.0](https://arxiv.org/abs/2601.11868)（2026） | 长程 CLI 任务；多个模型/agent harness | 多轮人工审计、human difficulty、trajectory/command 失败分类、LLM 标签与人类校准 | 为 DTBench 建立 trace taxonomy 的人工双标与一致性，LLM 只辅助分析、不决定主分 |
| 29 | [LongCLI-Bench](https://aclanthology.org/2026.findings-acl.1497/)（Findings of ACL 2026） | 20 个从 1000+ 候选中筛选的长程 CLI 工程任务；跨模型/agent 对比 | fail→pass 与 pass→pass 双测试；step-level progress；self-correction、plan injection 与交互指导 | source provenance、回归检查和 partial progress 能减少“记忆答案”与全有全无评分；诊断干预应比较恢复幅度 |
| 30 | [MLAgentBench](https://proceedings.mlr.press/v235/huang24c.html)（ICML 2024） | 13 个 ML 实验任务、7 类模型/agent | 计划与动作质量、task age/污染分析、性能改进过程 | 报告计划修正轨迹和数据污染审计；source benchmark 不是只用来装饰多样性 |
| 31 | [MLE-bench](https://arxiv.org/abs/2410.07095)（ICLR 2025） | 75 个 Kaggle 竞赛；模型 × scaffold；人类 bronze baseline | 资源 scaling、运行时间/成本、污染和竞赛难度 | 控制资源预算并画质量—成本 Pareto；资源放宽不能当纯 controller 消融 |
| 32 | [PaperBench](https://openreview.net/forum?id=xF5PuTLPbn)（ICLR 2025） | 论文复现任务；多种 agents、oracle 与人类 | 专家编写层次 rubric；JudgeEval 校验模型 judge；依赖结构和任务切片 | DTBench verifier 必须通过人工 trace 验证、等价实现与 mutation 测试，而不是只说“程序化” |
| 33 | [ITBench](https://proceedings.mlr.press/v267/drouin25a.html)（ICML 2025） | 102 个 SRE/CISO/FinOps 场景；模型/agent 比较 | 领域、任务类型、复杂度和可解释指标切片 | 事件主题须跨多个 source/domain，否则 theme 效应与领域效应共线 |
| 34 | [TheAgentCompany](https://arxiv.org/abs/2412.14161)（NeurIPS 2025 Datasets & Benchmarks） | 模拟软件公司中的真实工作任务；多种 agent 基线 | 按岗位、平台、步骤、成本和失败类别分析 | 长程协作应报告任务类型/平台/控制失败异质性和真实运行成本 |
| 35 | [AgencyBench](https://aclanthology.org/2026.acl-long.337/)（ACL 2026） | 138 个真实任务、32 个场景，平均约 90 次工具调用和百万级 token；多模型/agent | 用户模拟器、Docker；效率、反馈自纠正、工具偏好和长上下文失败 | 超长轨迹中必须报告恢复行为、工具/动作偏好与有效上下文，而非只报最终成功 |
| 36 | [Vending-Bench](https://arxiv.org/abs/2502.15840)（2025） | 超长周期经营模拟，多次独立长运行比较模型 | 利润分布、极端崩溃、上下文饱和与行为时间序列 | 平均终分会掩盖动态 meltdown；用事件对齐曲线与 time-to-recovery 描述退化 |
| 37 | [UltraHorizon](https://arxiv.org/abs/2509.21766)（ICLR 2026 submission） | 多环境、超长 token/工具调用、模型与人类 | horizon scaling、上下文熵、错误类型和人类对照 | 增加并发宽度、依赖深度、event lag 的剂量—反应，而非只比较事件类别 |
| 38 | [SWE-bench-Live](https://arxiv.org/abs/2505.23419)（2025） | 1319 个 2024 年后真实 issue、93 个 repository；多种 agent framework/LLM，在受控条件下与静态 SWE-bench 比较 | 自动更新与 Docker 化；按 repository origin、issue recency 和 task difficulty 分析 | held-out source/date、可更新 case 池和难度校准有助于证明 Async 退化不是污染或题目时期造成 |

### 3.4 多 Agent、协作与编排

| # | 论文 | 主实验与比较 | 最重要的分析设计 | 对 DTBench 的直接启示 |
|---:|---|---|---|---|
| 39 | [MultiAgentBench](https://aclanthology.org/2025.acl-long.421/)（ACL 2025） | 多领域协作任务；不同模型、agent 数、通信拓扑与规划策略 | 同时给 task score 与 coordination score；star/tree/graph/chain；agent 数和迭代次数 | task outcome 与 orchestration 分离；拓扑/规模只能作为受控结构因素，不能替代动态事件 |
| 40 | [GAIA2](https://arxiv.org/html/2602.11964)（ICLR 2026） | 固定 ReAct scaffold，多模型，每场景 3 次，7 个 capability split | verifier 在 450 条人工轨迹上校准；default/instant time；噪声梯度；main/app model 2×2；A2A collaborator ratio | 最值得复用：固定 scaffold、verifier validation、instant-time、主/子模型交叉与噪声剂量反应 |
| 41 | [Collaborative Gym](https://arxiv.org/abs/2502.16548)（ICLR 2026） | 人—Agent—环境异步协作；自主与协作、多模型对比 | user simulator 与真实用户验证；outcome 与过程协作指标 | 异步交互需要验证模拟器/事件引擎与真实行为的一致性，并区分自主能力与协作增益 |
| 42 | [ClawArena-Team](https://arxiv.org/html/2606.31174)（arXiv 2026，未检索到正式发表） | 41 个场景、258 轮、72 次 staged updates；固定 worker pool，只改变 12 个 manager models | SMS 同时度量 task completion、并行、结果利用、worker 利用和 communication；权限瓶颈、成本 Pareto、编排风格与陈旧信念错误分析 | 固定 worker 隔离 manager 是强诊断；staged update 与 stale belief 是最近邻，但其单次运行和偏描述性更新分析可由 DTBench 的配对因果设计超越 |
| 43 | [OrchBench](https://arxiv.org/html/2607.25656)（arXiv 2026，未检索到正式发表） | 240 个 DAG，4 个来源、10–100 节点并扩至 1000；9 个模型；确定性计划模拟 | 质量、关键路径时间、串行归一 token；用 Claude Code 实执行验证模拟器（相关约 .816）；跨 Claude Code/SWE-mini/OpenHands/Crush；agent/context budget sweep | 若使用 replay/simulator，必须用真实 source-native 执行验证；并发规模、关键路径与 transfer coverage 应纳入结构切片 |
| 44 | [DecisionBench](https://arxiv.org/html/2605.19099)（arXiv 2026） | GAIA、τ-bench、BFCL multi-turn；11 模型、5 条件、23,375 实例 | 20/80 profile/eval split；blind/aware 条件；aware-tool-only 单变量消融；5000 次 paired bootstrap；混合效应；反事实 delegation ceiling | 最值得复用：严格一变量干预、按 task ID 配对、过程/结果解耦，以及 profile 数据与正式评估隔离 |
| 45 | [MA-Gym / Manager Agent](https://arxiv.org/abs/2510.02557)（2025） | 多工作流中的动态 graph editing 与 manager 决策 | 按偏好、约束、目标、stakeholder 与 runtime factors 分析；对 manager 行为做细分 | 管理行为需要按触发因素和图编辑动作分析，但该类系统性组件消融不应强套到 DTBench case taxonomy 上 |

> 计数说明：CRAB 横跨 GUI 与 multi-agent 两类但只计一次。以上为 45 篇唯一 benchmark/评测论文；将下一节的 MAST 失效分析计入核心评测证据后，共 46 篇。

### 3.5 补充：与动态编排直接相关的系统/失效分析

| 编号 | 论文 | 实验作用 | 对 DTBench 的意义 |
|---:|---|---|---|
| 46 | [Why Do Multi-Agent LLM Systems Fail? / MAST](https://arxiv.org/abs/2503.13657)（2025） | 跨 5 个框架、150+ 任务，由 6 位专家归纳 14 类失效；报告人工一致性，并验证自动失效标签 | DTBench 的错误分析应以人工双标 taxonomy 校准；重点区分 specification、inter-agent misalignment 与 task-verification 三层 |
| S1 | [AgentOrchestra](https://arxiv.org/abs/2506.12508)（2025） | hierarchical manager 与 flat/monolithic 配置跨 benchmark 对比并做机制消融 | 可以作为系统对比背景，但不应成为 DTBench 的主 baseline：系统变化过多，难隔离动态重规划构念 |
| S2 | [DynTaskMAS](https://arxiv.org/abs/2503.07675)（2025） | 动态任务图、异步并行系统；比较时间和资源 scaling | 证明动态图系统值得研究，但属于被测系统而非 benchmark 的构念对照 |

---

## 4. 文献中最有效的实验范式

### 4.1 不是“更多模型”，而是可归因的比较

高价值实验普遍满足至少一个条件：

1. **同一任务的单变量反事实**：DecisionBench 的 aware-tool-only、τ²-bench 的 Oracle Plan、GAIA2 的 instant/default time。
2. **固定外部能力，只测目标能力**：ClawArena-Team 固定 worker pool；BrowserGym 固定 scaffold。
3. **结果与过程分离**：AppWorld、ST-WebAgentBench、MultiAgentBench、DecisionBench。
4. **把平均分拆为结构性曲线**：AndroidWorld 的方差分解、GAIA2 的噪声梯度、OrchBench/UltraHorizon 的规模扩展、τ-bench 的 pass^k。
5. **先验证评测器再解释模型**：GAIA2 verifier calibration、PaperBench JudgeEval、Terminal-Bench 人工审计。
6. **用真实运行校验代理评测**：OrchBench 用 source agent execution 验证 simulator；Collaborative Gym 用真实用户检验 simulator。
7. **提供 ceiling 和 lower bound**：GAIA/OSWorld 的 human、MLE-bench 的人类 bronze、DecisionBench 的反事实 delegation ceiling、oracle plan。

### 4.2 最能体现研究意义的实验通常回答“为什么”

| 研究主张 | 最有说服力的实验 | 仅有主表为什么不够 |
|---|---|---|
| 异步本身造成困难 | 同实例、同任务语义、同预算的 Linear/Async 配对 | 不同任务集的绝对分无法排除题目难度 |
| 困难来自动态重规划而非 worker 质量 | frozen event tape；perfect-worker 单变量替换；main/worker 2×2 | 端到端失败可能只是子 Agent 做错了 |
| 困难来自完成顺序与迟到权威信息 | canonical-order、instant-return、event lag 梯度 | 只按 event type 切片不能建立因果 |
| Agent 能看到事件但不能正确修订计划 | 阶段漏斗、affected-set precision/recall、obsolete-work rate | 总 D 分无法定位事件摄取还是 closure 出错 |
| benchmark 测到真实构念 | 人工/Oracle ceiling、verifier agreement、equivalent solution 与 mutation | 自动程序通过不必然等于科学有效性 |
| 方法在规模上仍成立 | 并发宽度 × 依赖深度 × invalidation breadth 剂量反应 | 固定小任务上的平均提升可能不能外推 |
| 改进不是靠无限等待/成本 | 质量—延迟—token—wasted work Pareto | 单一 success rate 会偏爱 Wait-All 或无界重试 |

---

## 5. 对当前《实验设计.md》的审计

### 5.1 已经正确、应当保留的部分

1. **主结果采用 Linear vs Async**：这是 DTBench 最强的因果识别基础。
2. **动态控制 D 与语义任务 S 分离**：比把所有指标压成一个分数更符合研究动机；`DTScore=0.8D+0.2S` 保持 secondary 即可。
3. **case-specific causal decision group**：解决不同事件主题没有同一组固定动作机会的问题，也避免把日志微事件直接微平均。
4. **控制策略与条件化诊断分组**：概念上已经比传统“组件消融”正确。
5. **benchmark design/evaluator evidence ablation 独立成组**：符合 benchmark 论文需要证明测量设计而不是只排模型榜单的要求。
6. **source-native 环境、私有真值、hidden verifier、invalid episode 与 model failure 分账**：是论文可信度的重要资产。

### 5.2 当前仍可能被审稿人追问的六个缺口

#### 缺口 A：策略差异仍可能被 worker 随机性污染

端到端运行时，不同 controller 可能获得不同 worker 结果、延迟和完成顺序。即使同一个 seed，也可能因 controller 的派发时点改变事件轨迹。因此 `Greedy vs Wait-All vs Version-Aware vs Model-Native` 的差异不完全是策略因果效应。

**优化：增加 Frozen Event Tape Controller Track。**

- 预先生成并冻结 worker payload、正确性、completion ID、到达时间、版本和权威关系；
- 每个 controller 接收同一事件带，只允许 controller 决定等待、接纳、拒绝、取消、重新派发、验证与提交；
- 比较 D、S、wall-clock proxy、obsolete worker time、unnecessary cancellation；
- 再在 10%–20% 的代表性 source-native cases 上跑真实端到端验证，报告 replay 与 E2E 的 rank/effect correlation。

该轨道不是 leaderboard 主结果，而是识别控制策略因果效应的实验装置。

#### 缺口 B：D 总分虽细，但论文叙事仍缺少闭环阶段证据

建议把 case-specific decision group 映射到统一的五阶段漏斗：

1. `Event Intake`：是否注意、ack、正确归属新结果；
2. `State Revision`：是否识别 authority/version/staleness/conflict；
3. `Affected-set Identification`：应失效/保留哪些 downstream artifacts/tasks；
4. `Plan Revision`：wait/cancel/redelegate/continue/merge 的动作是否适当；
5. `Closure`：是否重新验证、完成 reopen、拒绝迟到陈旧结果并正确提交。

必须使用**机会条件分母**：例如 cancellation recall 只在确实应取消的 case/action 上计算；同时报告 unnecessary-cancel rate。建议给出：

- 每阶段 unconditional pass；
- `P(stage k pass | stage k-1 pass)`；
- 首个失败阶段分布；
- 从 event 到第一次正确 plan revision 的 turns/time；
- 从 event 到恢复有效进度峰值的 time-to-recovery。

#### 缺口 C：部分诊断条件不是严格单变量

| 当前条件 | 主要混淆 | 建议的严格定义 |
|---|---|---|
| `Async-no-event` | 删除事件也删除动态决策机会 | 只作为“并发/上下文税”的 S、成本和有效率诊断；不沿用 Full Async 的 D 分母 |
| `canonical-order` | 可能同时改变 lag 和截止时间 | 保持 payload、绝对/虚拟时间预算、任务图不变，只置换合法 arrival order；仅在 order-sensitive case 上比较 |
| `perfect-worker` | 可能同时改变 payload、时延和行为长度 | 只替换 worker payload correctness，保留长度、角色、arrival time、版本和事件 schedule |
| `dependency oracle` | 若启动时给全图，会同时改变初始规划 | 仅在事件到达时公开“受影响 closure”，不公开未来事件、最佳动作或最终答案 |
| `resource relaxation` | 同时改变可并发数、时间、token、失败率 | 主文替换为 `instant-return/fixed-virtual-time`；并发槽位、token、deadline 分别在附录做单变量 sweep |
| `centralized` | 改变架构、可见信息、通信和权限 | 降为 exploratory/appendix；除非能固定信息集并只改变执行位置，否则不作核心因果结论 |

#### 缺口 D：缺少明确的负对照与“不过度重规划”证据

DTBench 的研究意义不仅是遇到变更要重规划，还包括**只重规划真正受影响的部分**。建议加入四类 evaluator-owned negative controls：

- irrelevant update：不应取消或使无关 artifact 失效；
- duplicate completion：不得重复产生副作用或覆盖新版本；
- equivalent fresh/stale payload swap：内容相同但 lineage/version 不同，必须以权威关系决定；
- independent branch completion reorder：相互独立分支换序，不应改变最终有效状态。

核心指标增加：affected-set precision/recall、over-invalidation rate、obsolete-work ratio、duplicate-side-effect rate。这样可以区分“什么都重做”的保守策略和真正的选择性重规划。

#### 缺口 E：重复运行尚未充分区分两种不确定性

建议在 core diagnostic subset 上做嵌套重复：

- **model variance**：固定 event tape/schedule，改变模型采样 seed；
- **environment variance**：固定模型/worker payload，改变合法 completion order、event lag 或 schedule seed；
- 使用 family-cluster paired bootstrap，先按 family 采样，保留 family 内 instance/repeat/mode 配对；
- 辅助混合效应模型：`point_pass ~ model * mode + event_theme + severity + (1|family/case)`；
- 报告 mean、95% CI、`pass^2/pass^3`，以及 model/schedule/family 方差占比。

#### 缺口 F：benchmark validity 证据应该进入主文，而不只在附录

建议主文至少保留一个小表：

- 100–200 条轨迹的双人标注与 adjudication；
- D 关键 observer 的 precision/recall/F1 或 agreement；
- equivalent implementation acceptance；
- mutation family kill rate 与 false positive；
- Oracle/Scripted controller 成功率；
- human operator 在 30–60 个诊断 case 上的 S、D、时间；
- case valid episode rate、event exposure rate、各能力真实机会数。

这张表回答“benchmark 真测到了异步动态重规划吗”，其重要性不低于模型排行榜。

---

## 6. 建议的“环环相扣”实验主线

### 6.1 七个研究问题与证据闭环

| 顺序 | 研究问题 | 核心实验 | 主 estimand / 指标 | 下一环如何承接 |
|---:|---|---|---|---|
| RQ0 | Benchmark 是否有效地测量目标构念？ | oracle/human、verifier 人工校准、equivalent/mutation、机会覆盖 | oracle/human ceiling；observer P/R；mutation kill；valid/exposure rate | 先排除评测器和 case 无效，才能解释模型差异 |
| RQ1 | 相同任务变为异步后是否系统退化？ | 同 family/instance 的 Linear vs Async；固定 scaffold/预算；随机 paired mode order | `ΔS=S_async-S_linear`；Async D；critical-failure rate；family-cluster CI | 若存在退化，继续问由哪些事件结构造成 |
| RQ2 | 哪类事件和严重度造成退化？ | 8 event themes；event lag、invalidation breadth、dependency depth、concurrency width 梯度；canonical-order | paired drop；dose-response slope；theme-macro | 若定位到事件结构，继续找控制闭环首个断点 |
| RQ3 | 主 Agent 在闭环哪个阶段失败？ | 五阶段 opportunity-conditioned funnel；event-aligned trace | 条件通过率、first-failure stage、reaction latency、time-to-recovery | 若知道断点，继续区分是 controller 还是外部条件导致 |
| RQ4 | 瓶颈来自 manager、worker、时序还是依赖知识？ | frozen tape；perfect-worker；instant-return；dependency oracle；main×worker 2×2 | 各干预的 paired recovery；交互效应 | 若 controller 是主要瓶颈，再比较控制策略 |
| RQ5 | 哪种控制策略改善正确性且代价合理？ | Model-Native、Greedy、Wait-All、Version-Aware、Oracle；先 replay 后 E2E | D/S、latency、token、obsolete work、over-invalidation Pareto | 得到策略 trade-off 后检验规模和鲁棒性 |
| RQ6 | 结论是否可靠、可扩展、跨来源成立？ | sampling/schedule 方差分解；pass^k；source/model holdout；规模 sweep；leave-one-theme-out | CI、方差占比、rank stability、cross-source heterogeneity | 完成对内部效度、外部效度和可靠性的闭环 |

### 6.2 建议只预注册三个 primary contrasts

为了避免“实验很多但主张发散”，主文 primary statistical tests 建议限制为：

1. **Async vs Linear**：同实例配对的语义退化与 Async 动态控制表现；
2. **Full Async vs Canonical Order**：仅在顺序敏感 subset，识别异步到达次序的因果代价；
3. **Full Async vs Perfect Worker / Dependency Oracle**：在预注册诊断 subset 上区分 worker-quality 与 dependency-revision 瓶颈。

控制策略比较、severity 曲线、其他诊断和 benchmark ablation 报效应量与 CI，但可定义为 secondary/exploratory，减少多重比较和故事线漂移。

### 6.3 主文建议的 3 表 4 图

**表 1：Benchmark validity 与数据构成。** case/family/source/theme/severity/机会数、oracle/human、verifier agreement、mutation/equivalent、valid episode rate。

**表 2：主结果。** 各模型 Linear S、Async S、配对 drop、Async D、critical fail、pass³、成本；不要只列 DTScore。

**表 3：Controller policy Pareto。** frozen tape 与 source-native E2E 并列，报告 D/S、latency、tokens、obsolete work、over-invalidation。

**图 1：研究构念和实验因果链。** `Async event → belief/state revision → affected-set → plan action → closure → semantic outcome`，并标出每个实验干预哪条边。

**图 2：事件主题 × 五阶段漏斗热图。** 直接显示 delayed authority、stale、conflict、failure 等分别击穿哪个阶段。

**图 3：Event-aligned shock/recovery curves。** 事件到达为 `t=0`，画有效进度、无效进度、obsolete work、恢复时间。

**图 4：Severity/Pareto 图。** 一侧为 lag/depth/breadth/concurrency 的剂量反应，另一侧为质量—延迟—浪费 Pareto。

---

## 7. 基线和消融的最终定位

> 对应的示意性预期数据、论文图表布局和反证判定标准见 `docs/实验图表预期设计.md`。其中所有数值仅用于预演结果结构，不能代替真实实验。

### 7.1 主基线

- **Linear**：核心构念反事实，不是普通 agent baseline；
- **Model-Native Async**：被测模型在固定 Track A scaffold 中的自然控制策略；
- **Oracle**：ceiling，不参与“公平模型排名”。

### 7.2 控制策略基线

- **Greedy**：任何可用结果到达就立刻推进；衡量低等待、高陈旧风险端点；
- **Wait-All**：一批任务全部结束再整合；衡量保守同步化端点；
- **Version-Aware Controller**：使用公开 version/lineage 规则过滤陈旧结果，并做预定义的局部失效/恢复；衡量显式状态策略能否填补 model-native 控制缺口；
- **Model-Native**：不外加确定性 controller；
- **Oracle**：使用 private event truth/affected closure 的上界。

这些是**策略对比**，不是 benchmark 消融。最好先在 frozen event tape 上比较，再在小规模 E2E 子集复现。

### 7.3 Benchmark 设计消融

当前四个方向基本合理：

- Semantic-Only：证明只看终态会漏掉 false success；
- Process-Only：证明过程分不能替代真实任务成功；
- Point-Micro：证明简单微平均被高检查点 case 支配；
- Unpaired：证明不配对会放大家族/实例难度混淆。

建议增加两个只在附录执行的设计消融：

- **No negative controls**：展示不加入 irrelevant/duplicate minefield 时，保守全重做策略为何会被高估；
- **No opportunity conditioning**：展示按 case 标签聚合如何误读某种 capability 的真实通过率。

### 7.4 不应再做的传统“组件消融”

不要把 `Cancel / Explicit Wait / Result Acknowledgement / Artifact Lineage / Version Metadata / Selective Invalidation / Verification Reopen / Structured Result Contract` 写成同一个 Manager 的 `Full − module`，因为它们在当前 benchmark 中属于：

- 不同 case 的动作机会；
- evaluator/kernel 的证据与协议；
- 输入元数据；
- 评分行为；
- 公开结果契约。

它们不是一个统一被测架构中可独立开关的同层模块。更合理的是按真实机会集做 case-conditioned contrast、metadata representation perturbation 或 evaluator evidence ablation。

---

## 8. 实施优先级与预算控制

### P0：投稿主线必须完成

1. Benchmark validity 小表：oracle/human、verifier agreement、mutation/equivalent、机会覆盖；
2. Linear vs Async 的 family-cluster paired inference；
3. 五阶段 funnel + first-failure stage；
4. event theme 与 severity 的核心切片；
5. Model-Native、Greedy、Wait-All、Version-Aware、Oracle 的 frozen-tape comparison；
6. 代表性 source-native subset 的 E2E validation；
7. pass³、valid episode rate、成本和 obsolete work。

### P1：强烈建议，有助于把论文从“新数据集”提升为“控制流诊断研究”

1. event-aligned shock/recovery curves；
2. perfect-worker、instant-return、dependency oracle 的严格单变量诊断；
3. main×worker 2×2；
4. model variance vs schedule variance；
5. irrelevant/duplicate/independent reorder negative controls；
6. source/theme/difficulty 的混合效应与 leave-one-theme-out。

### P2：预算充足再做或放附录

1. centralized 条件；
2. 多档 token/slot/deadline resource sweeps；
3. 多种事件文本/结果 schema 表示扰动；
4. Claude Code、SWE-mini、OpenHands 等完整外部框架横向比较；
5. 100–1000 节点的极端 DAG scaling。

外部框架并非没有价值，但它们同时改变 model、prompt、memory、tooling、worker policy、权限与异常恢复。对 DTBench 的核心构念识别而言，其优先级低于固定 scaffold、固定 worker 和 frozen event tape。可以选 2–3 个作为 external validity demonstration，不宜作为主因果基线。

---

## 9. 对论文写作结构的建议

实验章节可按以下顺序组织：

1. **Experimental Contract**：Track A、固定 scaffold、环境、模型、预算、重复和统计；
2. **Benchmark Validity**：human/oracle、verifier、mutation/equivalent、机会覆盖；
3. **RQ1 — The Async Gap**：Linear vs Async；
4. **RQ2 — What Events Break Agents**：theme、severity、canonical order；
5. **RQ3 — Where the Control Loop Breaks**：五阶段漏斗与恢复曲线；
6. **RQ4 — What Causes the Failure**：frozen tape、perfect worker、instant time、dependency oracle、main×worker；
7. **RQ5 — Can Explicit Controllers Help**：策略 Pareto 和 E2E validation；
8. **Reliability and Generalization**：pass^k、方差分解、cross-source/model、leave-one-theme-out；
9. **Benchmark Design Ablations**：为何双层、因果 group、配对与私有 evaluator 必要；
10. **Qualitative Cases**：只选能展示“迟到权威结果推翻当前假设”“冲突整合”“过期回流”“选择性失效”的 3–4 个代表轨迹。

这样的顺序能让每一节都回答上一节自然产生的问题，而不是把主结果、基线、诊断和消融平铺为互不相干的表格。

---

## 10. 最终建议

DTBench 不需要通过加入大量通用 ReAct/Claude Code/SWE-mini 基线来证明价值。最强的论文定位应是：

> 现有 benchmark 多数测量 Agent 最终能否完成长程任务，少数多 Agent benchmark 测量静态分工、通信或预先生成的编排计划。DTBench 通过同一任务的 Linear/Async 因果配对、evaluator-owned event truth、真实异步完成、动态决策机会与结果—过程双层验证，隔离并诊断主 Agent 在异步事件驱动控制闭环中的状态修订、选择性失效、重调度、等待、取消和恢复能力。

论文实验的决定性证据应是：

1. Async 相对 Linear 出现稳定、配对、跨来源的退化；
2. 退化随 event lag、依赖深度、失效宽度或并发宽度呈剂量反应；
3. 阶段漏斗显示退化集中在 state revision / affected-set / closure，而非一般工具能力；
4. frozen tape、perfect worker、instant time 与 dependency oracle 能把 worker、时序和知识瓶颈拆开；
5. Version-Aware 等显式 controller 在正确性—延迟—浪费 Pareto 上改善，但仍与 oracle 有明确缺口；
6. verifier、人类、mutation、等价解和 source-native E2E validation 证明这些现象不是评分器或模拟器伪影。

这六项形成的证据闭环，比单纯增加模型数量或框架数量更能体现研究意义。
