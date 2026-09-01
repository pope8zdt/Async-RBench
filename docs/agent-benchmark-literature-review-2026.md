# Agent Benchmark 论文调研与 Async-RBench 实验设计建议

> 调研截止：2026-08-28。本文区分“排行榜主实验”和“用于解释结果的分析性实验”；后者才是本报告的重点。

## 1. 结论先行

Async-RBench 已经具备不少高于常见 agent benchmark 的设计：同实例 `linear/async` 配对、固定 scaffold、隐藏程序化验证、语义结果与控制流双层评分、私有事件真值、8 个 case family（`primary_event_theme`）等权宏平均、等价解与 mutation gate、以及完整轨迹审计。

真正需要补强的不是再增加一个总分，而是把论文的中心因果问题说清并识别出来：

> 在基础任务、模型、子任务集合和预算保持不变时，异步结果到达与过期/冲突/失败事件，给“检测变化—修订依赖—选择性作废—重新验证—闭环交付”造成了多大额外损失？损失来自模型、worker 质量、事件时序、scaffold，还是验证器？

最优先的五项修改：

1. **不要用当前 combined X 的 `linear X - async X` 作为唯一“重规划下降”指标。** 当前 linear 与 async 的适用点集合不同：async 独有控制流点，两个 X 的分母和构成并不相同。应新增“shared semantic points 上的配对下降”，同时单独报告 async-only control-flow score；combined async X 可以继续作为 leaderboard 总分。
2. **把 GAIA2 设为最近邻基准正面对比。** GAIA2 测异步手机环境中的广义执行、时间、噪声、歧义和 A2A；Async-RBench 的差异应收紧为“异步 worker 结果集成的反事实因果评测”，尤其是同实例 linear/async、staleness、selective invalidation、reverification 和 obsolete work。
3. **增加 τ²-bench 式瓶颈分解。** 在一个平衡子集上增加 centralized/no-worker、oracle dependency plan、perfect worker result 三种诊断条件，分别隔离基础推理、协作通信、依赖修订和 worker 执行质量。
4. **增加 AndroidWorld 式方差分解。** 区分同一 schedule/instance 的采样随机性与不同 completion order、event lag、参数实例造成的环境随机性；只报告三次重复的均值不足以说明可靠性。
5. **修正统计推断层级。** headline 是 8 个 case family 等权宏平均，但 paired-drop 仍需保留 case_id/instance/repeat 的嵌套结构。置信区间应先形成 family 内 case 平衡值，再在 family 层做敏感性分析，或使用 point/episode 嵌套在 instance、case_id、case family 中的层次模型。

## 2. 论文版图：经典基准提供了什么分析套路

更早的环境型基准奠定了今天 agent evaluation 的基本范式：[ALFWorld](https://arxiv.org/abs/2010.03768) 把抽象文本策略与具身环境对齐，[WebShop](https://arxiv.org/abs/2207.01206) 用真实商品与可扩展网页环境研究组合约束、探索和 sim-to-real，[InterCode](https://arxiv.org/abs/2306.14898) 则把“代码动作—执行反馈”标准化为可复现 Docker 交互。它们的重要遗产不是某个仍然有效的排行榜数字，而是 environment feedback、长程稀疏 reward、组件 ablation、human trajectory 和可执行验证。

### 2.1 从“只看最终成功”到过程诊断

| 论文 | 评测对象与主验证 | 代表性的分析性实验 | 对 Async-RBench 的直接借鉴 |
|---|---|---|---|
| [AgentBench](https://arxiv.org/abs/2308.03688)（ICLR 2024） | 8 个交互环境、环境原生 reward/success | 29 个模型；按 TLE、context overflow、invalid format、invalid action 分解；代码训练与 alignment 对比；规划/自纠错案例 | 建立一级失败树，先分“没进入机会、格式/协议失败、超预算、决策失败、验证失败”，否则轨迹标签会混在一起 |
| [GAIA](https://arxiv.org/abs/2311.12983)（ICLR 2024） | 466 个需要浏览、工具、多模态的可核验问答；三档难度 | 人类与模型差距、按 level 分层、保留 300 个答案用于私有榜单 | 增加 human/oracle ceiling；公开任务、隐藏关键真值；让任务对人简单但对 agent 的动态整合困难 |
| [WebArena](https://arxiv.org/abs/2307.13854)（ICLR 2024） | 可复现网站中的 end-state 功能正确性 | CoT ablation；“提示不可完成”开关；可完成/不可完成分层；同模板不同实例的一致性 | 测 prompt/scaffold 敏感性；把“拒绝过期结果”与“过早放弃有效结果”同时计分，避免单向激励 |
| [SWE-bench](https://arxiv.org/abs/2310.06770)（ICLR 2024） | 真实 GitHub issue，测试套件验证 patch | BM25 vs oracle retrieval；context 长度和 collapsed context；repo/日期切片；patch 大小、文件数、函数数；定性失败分析 | 用 oracle ablation 定位瓶颈；报告输入/轨迹规模；验证 async 下降不是基础任务定位难度造成的 |
| [AgentBoard](https://arxiv.org/abs/2401.13178)（2024） | 9 环境；人工子目标形成 progress rate | progress metric 与人评相关性验证；hard/easy；progress-vs-step；grounding、memory、planning、world model、reflection 等子技能 | 画“事件对齐的进度曲线”：事件前获得多少、事件后丢失多少、多久恢复；只看终态会漏掉回退和低效恢复 |

这组经典工作的共同演化是：成功率仍保留，但论文价值主要来自“为什么成功/失败”的受控切片。Async-RBench 已有比它们更细的 event truth 和 control-flow observer，应该充分利用，而不是最终仍只展示一个 X。

### 2.2 可执行环境、稳健性与验证器

| 论文 | 分析设计 | 可迁移方法 |
|---|---|---|
| [OSWorld](https://arxiv.org/abs/2404.07972)（NeurIPS 2024） | screenshot、accessibility tree、SoM 等 observation ablation；人类耗时定义难度；single-app vs multi-app；分辨率、history、UI noise、跨 OS 分析；执行错误分类 | 固定模型后做 scaffold/observation sensitivity；用人类耗时或操作数校验结构难度；按跨 workstream/dependency breadth 切片 |
| [AndroidWorld](https://arxiv.org/abs/2405.14573)（ICLR 2025） | 参数化任务；固定参数做 20 次与变化参数做 20 次，分离模型非确定性和实例变化；跨 Android 版本；基础 prompt vs 增强 prompt | 对 completion order/event lag 采用相同方差分解；报告 schedule seed 的敏感性，而不是把一次真实完成顺序当成任务固有难度 |
| [ToolSandbox](https://arxiv.org/abs/2408.04682)（2024） | milestone DAG + minefield；state dependency、信息不足、canonicalization；干扰工具、schema 名称/描述/类型扰动；分析错误的 parallel calls 与 backtracking | 对 stale/duplicate/conflict 场景加入“不得发生”的 minefield；显式验证依赖顺序；做 event/result contract 表示扰动，检验是否靠表面提示词 |
| [AssistantBench](https://arxiv.org/abs/2407.15711)（2024） | 同时报 accuracy、answer rate、precision；closed-book/RAG/web-agent/fallback ensemble；准确率随轨迹长度；人工失败分类 | 增加 false-success、abstention/premature-stop 与 recovery-success；画性能随主 agent turn、事件位置和依赖深度的曲线 |
| [Terminal-Bench 2.0](https://arxiv.org/abs/2601.11868)（2026） | 每题多轮人工审计；人估难度与模型经验难度相关；trajectory-level 和 command-level 两层错误分类；LLM 标签先与人工校准并报告 agreement/precision/recall | 给 control-flow observers 做盲人评校准；结构难度必须与人类和经验难度对照；失败 taxonomy 要报告标注一致性而非只给案例 |

ToolSandbox 的 minefield 特别适合 Async-RBench：例如“旧 completion 不得进入最终 lineage”“无必要不得取消仍有效 worker”“duplicate delivery 不得触发第二次副作用”。这类负约束比事后从最终文件猜过程更可靠。

### 2.3 可靠性、协作和动态环境

| 论文 | 关键分析实验 | 对 Async-RBench 的含义 |
|---|---|---|
| [τ-bench](https://arxiv.org/abs/2406.12045)（2024） | `pass^k` 衡量同一任务连续 k 次都成功；function calling vs ReAct vs Act；移除 policy；按 write 次数；人工失败分解；成本 | 三次 repetition 除均值外至少给 `pass^2/pass^3`；对 compound event 数量、写入/提交次数做可靠性曲线 |
| [τ²-bench](https://arxiv.org/abs/2506.07982)（2025） | Default dual-control vs No-User vs Oracle-Plan；原始 vs workflow policy；按 action 数、subtask 数、issue type、persona；人工审计 simulator critical/benign error | 这是最值得复制的设计：用 centralized、oracle dependency、perfect worker 三个条件定位 async 损失；并对 evaluator/worker 模拟误差单独审计 |
| [MultiAgentBench](https://arxiv.org/abs/2503.01935)（2025） | task score 与 coordination score 分开；star/tree/graph/chain；planning strategy；iteration 1/3/5/7/10/20；agent 数 1/3/5/7 | 在诊断子集上做 worker 数、concurrency、拓扑和迭代预算敏感性；但不要让 LLM coordination judge 取代程序化主分 |
| [Vending-Bench](https://arxiv.org/abs/2502.15840)（2025） | 多次超长运行；比较利润分布、失控/meltdown；检验失败是否由 context fill 导致 | 加 time-to-derailment、首次不可逆 stale commit、恢复概率；不要把偶然一次成功视为长期可靠 |
| [TheAgentCompany](https://arxiv.org/abs/2412.14161)（2024） | 按平台和职业类别切片；成本/步数；复杂沟通、Office UI 和基础任务的错位；定性 common failures | 按源 benchmark、artifact 类型、协作宽度切片；人类觉得难与 agent 难往往不是一回事 |
| [GAIA2](https://arxiv.org/abs/2602.11964)（ICLR 2026） | 7 个 capability split；每场景 3 次；成本—时间—分数 Pareto；tool calls/tokens 相关；Time 的 instant/default ablation；A2A collaborator ratio；main/app model 2×2 | 必须做最近邻对比；加入 canonical-time/observed-time 辅助实验、main/child 交叉实验和 Pareto 图；避免把“推理更慢”误读成“不懂异步” |

GAIA2 与本项目的边界应写成：

- GAIA2 问“通用 agent 在异步动态环境中的综合能力如何”；
- Async-RBench 问“在同一基础任务与 workstream 集合下，仅改变并发与结果到达结构，会造成什么可归因的集成/重规划损失”。

要守住这个边界，`linear/async` 配对、共享点效应、stale lineage、selective invalidation、reverification 与 obsolete work 必须成为论文主角。

### 2.4 2026 的新趋势

- [AgencyBench](https://aclanthology.org/2026.acl-long.337/) 用平均约 90 次工具调用、1M token 的真实长程任务，分析资源效率、反馈驱动自纠错、工具偏好和 model×scaffold；说明 agent benchmark 已从“模型表格”转向“模型与执行框架共同决定表现”。
- [MCP-Universe](https://arxiv.org/abs/2508.14704) 使用真实 MCP servers，区分静态、格式和实时动态 evaluator，强调 unknown-tool、跨工具协调和动态真值。
- [DeepPlanning](https://aclanthology.org/2026.acl-long.335/) 强调局部约束与全局预算优化，并比较显式推理与 parallel tool use 的效果—效率权衡。
- [AppWorld-UL](https://arxiv.org/abs/2607.20536) 通过 ambiguity、confirmation、infeasibility 等 516 个 user-in-the-loop 任务，说明即使环境状态可验证，simulator 的知识边界和交互类型也必须被显式设计和分层报告。
- [From Confident Closing to Silent Failure](https://arxiv.org/abs/2606.09863) 说明 agent 自称完成与环境真值经常不一致，LLM judge 对 false success 的识别也不可靠；这进一步支持 Async-RBench 坚持程序化终态与控制流验证。

## 3. 对当前 Async-RBench 的设计审计

### 3.1 已经很强、应保留为论文卖点的部分

1. **同实例反事实配对。** 比跨任务比较更接近因果设计，且 mode order 已随机化。
2. **固定 Track A scaffold。** 减少“参赛者自带编排器”导致的不可比性；development track 也与官方结果隔离。
3. **程序化双层验证。** final semantic state 与 evaluator-observed control flow 分开，能识别“结果对但过程错”。现有 gpt-5.4 case 已出现 24/24 语义正确但控制流只过 2/4 的实例，这正是论文级现象。
4. **信息边界与 digest。** private truth、hidden verifier、容器隔离、case/verifier/scaffold digest 对可复现性很有价值。
5. **事件与能力分离。** event theme 是刺激，capability 是响应，概念上正确。
6. **mutation 与等价解。** 比只验证 canonical oracle 更能证明 verifier 没有锁死某个实现。
7. **case-family macro。** 8 个 case family 各占相同权重，避免 `delayed_authoritative_result` 因实例数量多而支配总分。

### 3.2 当前最重要的效度风险

#### 风险 A：配对下降混合了“模式效应”和“计分构成效应”

当前 async 注册额外 control-flow points，而 linear 中这些点 `not_applicable`。因此：

```text
current paired drop = linear(composition A) - async(composition A + async-only controls)
```

它不是严格的同一 outcome 上的反事实差。建议同时给出：

```text
Shared-Outcome Drop = linear(shared semantic points) - async(shared semantic points)
Async-Process Score = async-only control-flow passed / applicable
Async Combined X    = 现有 weighted combined score（可保留作排行榜）
```

这样可以形成四象限：结果对/过程对、结果对/过程错、结果错/过程对、两者都错。

#### 风险 B：capability breakdown 目前是“被该 capability 标记的 case 的整题 X”

`_capability_macro` 将一个多标签 case 的完整 X 同时归给每个 capability。这适合作为 `capability-conditioned case score`，但不能解释为该能力本身的 point pass rate。应新增按 `capability_target` 聚合的 `capability-targeted point score`，并保留前者作为上下文表现。

#### 风险 C：真实 completion order 提升生态效度，也引入 schedule luck

相同模型可能因网络、provider queue、worker 难度随机得到不同顺序。主实验可以继续用真实顺序，但需在平衡子集做：

- identical-order 重复：同一 canonical release trace 多次，测采样随机性；
- varied-order 重复：改变 order/lag，测环境随机性；
- observed-time vs logical-time replay：分离 provider latency 与决策质量；
- 报告 event arrival 相对首次 downstream commit 的位置，而不仅是绝对毫秒。

#### 风险 D：case family 只有 8 个，family 内 case_id 数量决定估计稳定性

case family 固定为 8 个 `primary_event_theme` 分类，不能通过把 case_id 攵称 family 来制造更多聚类。应报告每个 family 的 case_id 数、实例数和覆盖度，并在 family 内先做 case 平衡；仅以 8 个 family 作为 bootstrap cluster 时区间会不稳定，因此还应报告 leave-one-family-out 和层次模型敏感性分析。

#### 风险 E：bootstrap 层级与 headline estimand 不一致

当前 paired-drop bootstrap 按 `(case_id, instance_id, repeat, ...)` 组织配对，而 headline 是 case-family macro。应先在每个 family 内形成 case_id 平衡估计，再进行 family 层敏感性分析；辅助分析可用 point-level logistic mixed model：

```text
point_pass ~ model * mode + case_family + difficulty + schedule_severity
           + (1 | case_family:case_id) + (1 | case_id:instance_id) + (1 | point_id)
```

#### 风险 F：结构难度尚未获得外部校准

当前 difficulty 是 workstream、milestone、dependency、artifact、event 等结构计数，适合预注册，但不能单独证明真实难度。应像 Terminal-Bench/OSWorld 一样比较：

- 人类完成时间、错误率、操作数；
- oracle/controller 最短步数；
- 多模型经验 pass rate；
- 三者与结构分数的 Spearman 相关和分层校准图。

## 4. 建议的论文实验矩阵

### 4.1 主实验：保持简单、可解释

| 因子 | 建议 |
|---|---|
| 模型 | 8–12 个模型，至少 4 个独立模型家族；含强/中/弱、reasoning/non-reasoning、至少 2 个开源模型 |
| 模式 | 同 instance/seed/budget 的 `linear` 与 `async`；pair 内执行顺序随机 |
| 重复 | 全测试集至少 3 次；60-case core diagnostic subset 做 5 次以画 `pass^k` 与方差分解 |
| scaffold | Track A 固定 scaffold 为 headline；只在诊断子集做 scaffold sensitivity，不混入榜单 |
| 主指标 | `Async Combined X`、`Shared-Outcome Drop`、`Async-Process Score`、scenario construction rate |
| 可靠性 | pass^1、pass^2、pass^3；core subset 可到 pass^5；family-cluster 95% CI |
| 效率 | tokens、wall time、provider/model calls、obsolete tokens、X/token 与 Pareto frontier；避免只给一个易失真的“每美元分数” |

不要只给全局均值。预注册以下切片：8 event themes、3 scenario classes、8 capability targets、difficulty、source benchmark、dependency depth、invalidation breadth、event position 和 worker count。

### 4.2 诊断实验：用最少条件定位因果瓶颈

在 calibration/development 中选 60 个平衡实例，做以下条件：

| 条件 | 保持不变 | 改变 | 识别的问题 |
|---|---|---|---|
| Linear | task/workstreams/budget | 无初始 overlap | 基础任务上限 |
| Async-full | 同上 | overlap + 真实到达 | 真实异步总损失 |
| Async-no-event | overlap | 不制造 authority/stale/conflict 变化 | 纯并发/上下文管理税 |
| Async-oracle-dependency | Async-full | 事件后提供正确依赖/作废范围，不给最终答案 | 规划/依赖识别是不是瓶颈 |
| Async-perfect-worker | Async-full | worker payload 保证正确、完整、合约有效 | worker 执行质量对主 agent 的污染 |
| Centralized | 同信息与工具 | 主 agent 直接拥有 worker 工具，无消息协作 | 协作通信和结果集成开销 |
| Canonical-order replay | Async-full | 固定 release order/lag | 去除 schedule luck 后的模型差异 |

这是 τ²-bench 的 No-User/Oracle-Plan 思路在本任务上的对应物。条件较多，所以只用于诊断子集，不进入正式 leaderboard。

### 4.3 main/child 交叉实验

GAIA2 表明 main-agent 规划质量与 app-agent 执行质量都有独立贡献。建议在 30–60 个实例上做 2×2：

| | 弱 child | 强 child |
|---|---:|---:|
| 弱 main | 基线 | worker fidelity 增益 |
| 强 main | planning/critique 增益 | 上限 |

比较 final semantics、stale rejection、result-contract rejection、redelegation、token 和 wall time。该实验能回答 Async-RBench 到底测到“主 agent 重规划”还是“子 agent 产物质量”。

### 4.4 event severity 剂量—反应实验

每个事件不要只有类别标签，还应有可量化强度：

- event lag：结果在下游工作开始前/后多久到达；
- commit position：到达时已完成的 downstream milestone 比例；
- invalidation breadth：被作废 artifact/milestone 比例；
- dependency depth 与 fan-out；
- authority reversals 次数；
- overlap width / concurrent workers；
- deadline slack、剩余 token/turn budget。

对每种 theme 生成 3 档 severity，检验单调剂量—反应，而不是只比较 8 个类别的平均分。若难度不随 severity 单调，case 的构造效度值得复查。

## 5. 最应该画的分析图

1. **Event-aligned progress curve**：以 authority/event delivery 为 t=0，画 active-valid milestones 比例；同时画 invalidated progress、恢复到事件前峰值所需 turns。
2. **Outcome–process 四象限**：semantic pass 与 process pass 的 2×2，突出“24/24 final state 但 2/4 control flow”的真实样例。
3. **Reliability curve**：按模型画 pass^k；平均 X 相同的模型可能可靠性完全不同。
4. **Severity dose-response**：按 event lag、invalidation breadth、dependency depth 画配对 drop。
5. **Recovery survival curve**：事件后尚未完成正确恢复的比例，未恢复 episode 作为 right-censored/失败处理需预注册。
6. **Cancellation precision–recall**：该取消的是否取消；不该取消的是否被误杀。单独只报 recall 会鼓励过度取消。
7. **Cost/time/Pareto**：Async X、shared drop、tokens、wall time 和 obsolete-work ratio；不要仅报相关系数后做因果解释。
8. **Family-level forest plot**：每个 family 的 paired shared-outcome drop 与 CI，显示异质性。

## 6. 轨迹错误 taxonomy：建议与现有字段对齐

建议只用 evaluator 可观察证据做主标签：

1. **Opportunity/Protocol**：scenario 未构造、结果未暴露、contract rejection、预算耗尽。
2. **Detection**：未察觉新 authority、未识别 stale/duplicate/conflict/failure。
3. **Decision**：没有取消、误取消、错误 arbitration、错误 redelegation、作废范围过大/过小。
4. **Integration**：正确结果未进入 active lineage，stale 结果被保留，partial 覆盖 complete。
5. **Recovery**：恢复过慢、重复无效工作、replacement child 无效。
6. **Verification/Closure**：未 reopen、未 reverify、提前结束、最终 artifacts 不闭合。

对于需要人工/LLM 阅读轨迹的二级原因，先盲标 100–200 条，报告双人 agreement；再决定是否用 LLM 扩展。LLM 标签不得改变程序化主分。

## 7. 对数据集策略的具体建议

- 保留 450 instance 目标，但新增 `minimum_family_count >= 30`；更理想是 45–60。
- 事件 theme 可以近似均衡，但 headline 需同时报告 theme-macro，避免某些 family 结构影响总体权重。
- difficulty 配额保持预注册；冻结前用人类/经验难度校准，必要时只改 development/calibration，不看 test 后改阈值。
- 每个 capability 应保证足够的**可测机会数**，不仅是 case 标签数。对 cancellation/reverification 等报告 opportunity coverage 和有效分母。
- 每个 primary theme 至少有多个 source benchmark、多个 family 和多个 severity；否则 theme 与 domain 共线。
- human baseline 不需要跑满 360 test；可在分层抽样的 60–100 个实例上完成 linear/async，并记录时间、错误和主观负荷。

## 8. 论文叙事建议

推荐的核心 claim 是：

> Existing agent benchmarks measure whether agents eventually complete long-horizon tasks. Async-RBench isolates whether an agent preserves correctness when independently produced results arrive concurrently and revise the active dependency graph. Its within-instance linear/async counterfactuals, private event truth, and dual outcome/process verification quantify not only final failure, but stale lineage, selective invalidation, recovery, and reverification.

三条实证 RQ 足够支撑全文：

- **RQ1：异步执行是否产生独立于基础任务难度的可靠性下降？** 用 shared semantic paired drop + process score 回答。
- **RQ2：哪些事件结构和 severity 最容易击穿 agent？** 用 theme/capability/severity 层次分析回答。
- **RQ3：损失来自模型推理、worker 执行、协作编排还是时间/预算？** 用 centralized/oracle/perfect-worker/canonical-time/main×child ablation 回答。

如果这三问做扎实，Async-RBench 的贡献会比“再做一个覆盖很多 agent 任务的 benchmark”更清晰，也更不容易被 GAIA2、MultiAgentBench 或 Terminal-Bench 吸收。

## 9. 推荐阅读优先级

如果只精读 8 篇，顺序建议为：

1. [GAIA2](https://arxiv.org/abs/2602.11964)：最近邻与必须回应的差异。
2. [τ²-bench](https://arxiv.org/abs/2506.07982)：最好的瓶颈分解模板。
3. [AgentBoard](https://arxiv.org/abs/2401.13178)：过程进度与分析面板。
4. [ToolSandbox](https://arxiv.org/abs/2408.04682)：milestone/minefield/DAG 评分。
5. [AndroidWorld](https://arxiv.org/abs/2405.14573)：随机性与参数稳健性。
6. [τ-bench](https://arxiv.org/abs/2406.12045)：pass^k 和可靠性。
7. [Terminal-Bench 2.0](https://arxiv.org/abs/2601.11868)：任务审计、难度和轨迹 taxonomy 校准。
8. [SWE-bench](https://arxiv.org/abs/2310.06770)：oracle ablation 与上下文瓶颈定位。
