# 607 条生成 case 的正式任务改造可行性审计

## 结论

本轮审计回答的是“哪些源任务具有足够真值与任务结构，可以被真正改造成正式 Async-RBench case 任务”，而不是“哪些任务按当前残缺运行环境可以立即执行”。

- 审计输入：607 条源任务记录。
- 技术上可改造：607 条；因当前环境不完整而淘汰：0 条。
- 合并有真实依赖关系的 Terminal-Bench 上游任务后，可形成 604 个不同的正式任务方案：602 个单上游、1 个双上游、1 个三上游。
- 已达到正式 8 个任务的蓝图深度：607/607。每条固定为 24 个语义评分蓝图、4 个 case-specific 因果控制流评分蓝图，并有一一对应的定向 negative mutation 蓝图。
- 已经完成 Docker、事件注入、可执行 Oracle、隐藏测试、等价解、mutation execution、人工审核、校准和 registry 冻结：0 条。这里不能把“可改造蓝图”误称为“正式可运行任务”。

逐条结果位于：

- `artifacts/case-transformability-audit-v2/cases.jsonl`：607 条完整内部审计记录；
- `artifacts/case-transformability-audit-v2/case-index.csv`：便于筛选和查看的索引；
- `artifacts/case-transformability-audit-v2/summary.json`：汇总与 450 任务配额可行性证明。

## 输入构成与改造工作量

| 来源 | 源记录数 | 改造判断 | 主要补建内容 |
|---|---:|---|---|
| MultiAgentBench | 341 | 全部可改造 | MARBLE/数据库/协作服务运行时、真实角色结果释放、私有环境真值与 transcript observer |
| OSWorld | 91 | 全部可改造 | 固定桌面快照、GUI bridge、离线资产镜像、应用状态 observer、重启后闭环验证 |
| SWE-bench | 169 | 全部可改造 | pinned repo/base commit、官方测试环境、clean-clone worker、异步测试结果与 patch lineage |
| Terminal-Bench | 6 | 全部可改造 | 复用锁定任务包并组成 3 个任务方案，补 evaluator-owned 事件和 v9 评分合同 |

按当前工程距离划分：

| 改造路径 | 源记录数 |
|---|---:|
| 新写私有语义 Oracle，并重建 MultiAgentBench 服务运行时（coding/bargaining/research） | 243 |
| 重建已有私有 root-cause truth 的 MultiAgentBench 数据库运行时 | 98 |
| 重建 SWE-bench 官方测试运行时 | 165 |
| 重建 OSWorld 桌面运行时和资产 | 88 |
| 另写 OSWorld 私有 Oracle 并重建桌面运行时 | 3 |
| 运行包接近可复用，但仍需正式化 | 10 |

10 条“接近可复用”按合并后的任务方案计为 7 个任务，不表示已经能进入正式 registry。

## 原先误判为不可改造的 4 条

原审计错误地把 OSWorld 通用字段不完整当作缺少任务真值。复核后四条都可改造：

| case | 复核结论 |
|---|---|
| `osw-dependency-unblock-53a858f0f1` | GIMP 已有 `check_triangle_position` 和结果对象；该 evaluator 本来就不需要通用 expected 文件。 |
| `osw-dependency-unblock-b6a3a4e5a5` | Thunderbird 目标可由 `prefs.js`/account identity 图和本地 mock SMTP 观察，检查 outgoing-only 且没有 incoming service。 |
| `osw-dependency-unblock-e89ce4db78` | Chrome 目标可在固定版本中检查 Local State/Preferences、flag 状态和重启后行为。 |
| `osw-state-reconciliation-afd68ff774` | 可观察活动桌面用户，并对账户数据库做前后哈希，验证切换用户但不 logout、不改账户。 |

后三条需要新写 task-specific 私有 Oracle，但这属于允许补建的运行包工作，不需要发明新的源任务真值。

此外，243 条非数据库 MultiAgentBench 任务也必须新写私有语义 Oracle：coding 使用按源需求派生的功能/性质测试，bargaining 使用确定性 negotiation ledger 和条款约束，research 使用固定证据语料、claim/citation entailment 与 unsupported-claim 排除。连同上面的 3 条 OSWorld，共 246 条需要定制新 Oracle；它们仍然具有可改造所需的公开任务合同，但工程成本显著高于已有原生 gold/test 的任务。

## 异步情况分类

正式分类不再使用旧的 7 个 generation family。每条 case 的 primary event theme 由源任务的实际机制确定，例如：数据库专家结果冲突、议价 offer revision、代码测试/存储边界失败、桌面非幂等副作用、SWE 原生测试数量与测试文件闭包。

| Primary event theme | 候选记录数 | 论文目标数 |
|---|---:|---:|
| delayed authoritative result | 63 | 57 |
| late/out-of-order superseded result | 97 | 57 |
| partial-then-complete result | 73 | 56 |
| conflicting valid results | 98 | 56 |
| duplicate/replayed completion | 57 | 56 |
| child failure/implicit error | 56 | 56 |
| task scope/dependency change | 67 | 56 |
| straggler under resource pressure | 96 | 56 |

异步场景池为 result-eventful 281、live-eventful 192、resource-eventful 134。审计中给出了一个可构造的 450 任务配额分配，能同时满足论文的 8 个主题目标和 225/135/90 场景目标；因此候选数量与联合边际结构足够。该结论不替代正式任务实现和校准。

## 每条 case 内部审计内容

`cases.jsonl` 的每一行都包含：

1. 源任务绑定：instruction SHA-256、全部本地源文件路径与 SHA-256、原生 evaluator/测试/角色/环境锚点；
2. 任务深度：1–4 个上游任务、端到端 milestones、显式 dependency edges、保留工作与受影响闭包；
3. 异步设计：唯一 primary event theme、场景类别、分类理由、能力标签、可选备选事件；
4. 运行包计划：Docker/VM、固定资产、任务脚本、真实事件注入点、Oracle、隐藏测试和特殊 observer；
5. 语义评分：数量由任务中可独立验证的源事实决定，包括原生测试/角色/标签/artifact、事件影响、preservation、stale exclusion、lineage 和 closure；
6. 控制流评分：数量由事件真正产生的因果决策决定，由 Case IR 编译并覆盖适用的 event intake、state revision、plan revision、closure 阶段；
7. 有效性设计：每个控制点对应定向 negative mutation、must-fail 与 must-still-pass 局部性要求；
8. 正式化差距：运行包实现、Oracle/隐藏测试、等价解、mutation execution、人工审核、校准和 registry gate。

607 条的 semantic design digest 和 control design digest 均无重复；这证明没有整套复制评分蓝图，但不能代替后续相关性/退化点校准。

## 与正式 8 个任务的标准对照

正式 8 个任务均有 Dockerfile、task.yaml、private_case.yaml、任务脚本、事件计划、语义/控制流检查注册表、可执行测试和 provenance。607 条当前完成了内容派生的定制蓝图和 Case IR，仍需逐条物化并执行验证。

每个拟晋级任务必须依次完成：

1. 物化 Docker/VM、固定资产和 participant-visible task bundle；
2. 实现 evaluator-owned 的真实独立事件、释放时机和公开 receipt；
3. 将有独立证据的语义事实和因果决策写成数量可变、可执行且冻结的检查，不拆点凑数；
4. 实现 canonical solution 和至少 1 个等价解；
5. 接受前至少执行 2 个定向负 mutation，校准阶段每 case 至少执行 40 个；
6. 通过 Oracle、隐藏 verifier、public/private boundary、泄漏和 provenance 检查；
7. 完成真正的人工 case review；现有模型代理 review 不计入该门槛；
8. 完成至少 5 个模型、3 个模型家族、每模式至少 3 次的校准，并淘汰相关或退化评分点；
9. 冻结完整 bundle/verifier digest 后才写入 `cases/registry.json`。

## 验证

- 审计生成器：`python scripts/audit_case_transformability.py`；
- 自动测试：`uv run --with pytest --isolated pytest tests/test_case_transformability.py -q`；
- 结果：2 tests passed；逐条检查 607 条、内容派生的可变评分深度、Case IR/score plan schema、设计唯一性和 450 配额可行性。

当前机器的 Docker daemon 未运行，因此本轮无法重新执行正式 8 个任务的容器 Oracle 生命周期；该限制不影响本轮源任务改造可行性审计，但正式任务物化后必须在 Docker/VM 可用环境重新跑完整验证。
