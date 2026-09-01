# Async-RBench case 任务严格审计与重建报告 v1

审计日期：2026-08-31

## 1. 结论

本报告统一使用“case 任务”作为计数单位。`case_id` 是注册 family 标识，真正的任务单位是 `(case_id, instance_id)`。当前 `cases/registry.json` 注册的是 8 个正式 case 任务，且全部位于 `calibration` split；它们不是 7 个异步分类。

607 条新生成记录中的 `family`（例如 `dependency_unblock`、`late_constraint`）只是旧生产模板/来源标签，不能作为 Async-RBench 的 case 分类。正式异步分类必须同时包含：

1. 一个 `primary_event_theme`；
2. 一个 `async_scenario_class`；
3. 一组多标签 `capabilities`。

严格 fail-closed 审计结果：

| 范围 | 数量 | 结论 |
|---|---:|---|
| 新生成记录 | 607 | 0 条已经具备正式异步分类和完整发布合同 |
| 违反锁定来源政策 | 432 | 拒绝；341 条 MultiAgentBench、91 条 OSWorld |
| 缺原生可复现运行环境 | 171 | 暂存，不可改名为正式 case 任务 |
| 有原生运行证据、需逐任务重建 | 4 | 进入定制重建队列，不是正式入选 |
| 已完成技术重建的候选 | 1 | `nginx-live-port-conflict`，仍被独立人工复审门禁阻止晋级 |
| 当前新增 registry 任务 | 0 | 不伪造 review/calibration 证据，不绕过发布门禁 |

## 2. 正式发布门槛

一个生成记录只有同时满足下列条件，才可变成我们自己的 Async-RBench case 任务：

- 来源符合 `dataset_policy.json`，保留原任务指令和可追溯 provenance；
- 完整、可复现、容器化的原生任务运行包，不是 environment smoke 或文本壳；
- public/private 信息边界、结果合同、事件资产、observer 与泄漏审计完整；
- 明确登记八类事件主题之一、三类异步场景之一和适用 capabilities；
- 任务专属 Case IR：需求、依赖图、前后状态、影响闭包、保留边界、必需/禁止响应、可观测证据、局部反例；
- 任务专属语义检查和控制流检查；控制点必须落入任务因果 decision group，并带 local outcome anchor；
- canonical solution 与至少一个非规范等价解使用同一隐藏 verifier 全部通过；
- 至少两个定向 negative mutation 被 verifier 精确杀死，且不能依赖动作序列模板打分；
- Oracle、隔离 hidden verifier、scenario construction、Linear/Async 配对与 digest 门禁通过；
- 独立人工复审、source instruction fidelity、正式 approval 证据通过；
- 正式校准满足 `evaluation_contract.json`：至少 5 个 pilot 模型、3 个模型家族、每模型/模式至少 3 次重复、每 case 至少 40 个执行 mutation，并达到 kill-rate 与非退化阈值。

因此，“Docker 能启动”只等于 runtime smoke；“Oracle 能通过”也不等于 publication-ready。

## 3. 607 条生成记录的逐条审计结果

机器可读审计逐条保存了 607 行记录，每行包含来源、旧 family、运行包文件、模型证据、门禁、失败项和 disposition。

### 3.1 正式异步分类状态

| 状态 | 数量 |
|---|---:|
| 已正式标注 `primary_event_theme + async_scenario_class + capabilities` | 0 |
| 仍是未分类生成壳 | 607 |

旧生产 family 的数量仅作为 provenance 诊断保留：

| 旧生产 family（不是正式异步分类） | 数量 |
|---|---:|
| dependency_unblock | 204 |
| late_constraint | 158 |
| conflicting_specialist_results | 90 |
| late_test_evidence | 73 |
| cross_app_artifact | 48 |
| state_reconciliation | 28 |
| partial_failure_recovery | 6 |

不能机械地把这些 7 个名字映射到八类事件主题。每一条任务必须从任务因果结构、真实事件政策和影响闭包重新判定。

### 3.2 四条可进入定制重建队列的 SWE 记录

| 生成 case id | 原始 SWE 任务 | 当前判断 |
|---|---|---|
| `swe-dependency-unblock-3361c7af50` | `matplotlib__matplotlib-25332` | 原生 verifier 有证据；缺正式运行包、Case IR、分类、任务专属评分和足量重复 |
| `swe-dependency-unblock-8902c7f431` | `django__django-12125` | 同上 |
| `swe-late-constraint-3950516755` | `pytest-dev__pytest-7324` | 同上 |
| `swe-late-constraint-7ce47cda27` | `django__django-11815` | 同上 |

这四条现有 pilot 均只有每模型/模式 1 次配对重复，而且共享“diff 已持久化后测试 worker 晚到”的通用协议。该协议不足以证明四个任务拥有不同的任务因果异步决策点，因此必须逐条重建，不能批量复制评分模板。

## 4. 8 个正式 case 任务检查

8 个任务全部能构建、执行 Oracle，并通过隔离 hidden verifier；每个任务当前有 24 个语义检查和 4 个控制流检查。串行闭环实测结果为 8/8 通过。

| 正式 case 任务 | 来源 | 主事件主题 | 场景类 | runtime | 发布合同 |
|---|---|---|---|---|---|
| `data-recovery-service/seed-1` | Terminal-Bench | partial-then-complete | result-eventful | 24/24 通过 | 缺 Case IR、score plan、quality contract、等价解/反例执行证据 |
| `distributed-model-runtime/seed-1` | Terminal-Bench | delayed authoritative | result-eventful | 24/24 通过 | 同上 |
| `secure-release/seed-1` | Terminal-Bench | late/out-of-order superseded | result-eventful | 24/24 通过 | 同上 |
| `secure-release/tracebench-git-recovery-late-authority-001` | Terminal-Bench | late/out-of-order superseded | result-eventful | 24/24 通过 | 同上 |
| `gaia2-stockholm-moveout/seed-1` | GAIA2 | task scope/dependency change | live-eventful | 24/24 通过 | 同上 |
| `scheduler-selective-replan/seed-1` | Terminal-Bench | conflicting valid results | result-eventful | 24/24 通过 | 同上 |
| `git-conflict-and-cleanup-closure/seed-1` | Terminal-Bench | conflicting valid results | result-eventful | 24/24 通过 | 同上 |
| `swe-bench-selective-patch/seed-1` | SWE-bench | partial-then-complete | result-eventful | 24/24 通过 | 同上 |

这 8 个任务是可运行的已注册校准任务，但按当前 v9 论文标准，publication-ready 数为 0/8。原因不是语义 verifier 不工作，而是它们尚未补齐任务因果评分与质量验证合同。现有四个控制维度名字齐全，但 `decision_group` 为空，不能支撑论文要求的 case-specific causal-group 宏平均。

### 4.1 当前异步覆盖缺口

| 维度 | 当前覆盖 |
|---|---|
| primary event themes | 5/8 类 |
| 缺失主题 | duplicate/replayed completion；child failure/implicit error；straggler under resource pressure |
| async scenario classes | result-eventful 7；live-eventful 1；resource-eventful 0 |
| 难度 | 8 个均为 hard，缺 easy/medium 校准覆盖 |

所以 8 个任务可以作为现有校准基线，但不能证明完整实验设计覆盖已经达标。

## 5. 已完成的任务级重建：`nginx-live-port-conflict`

该候选来自 607 条集合中的 Terminal-Bench `nginx-request-logging` 来源任务，而不是凭旧 `late_test_evidence` family 直接分类。重建后分类为：

- primary event theme：`task_scope_or_dependency_change`；
- secondary event theme：`delayed_authoritative_result`；
- async scenario class：`live_eventful`；
- capabilities：`late_revision_adoption`、`selective_invalidation`、`verification_reopen`。

运行包包含三个独立 workstream、真实 8080 端口竞争、evaluator-owned authority receipt、选择性影响闭包、运行时 observer、隐藏验证和 lineage。24 个语义点是 Nginx 任务专属检查；4 个动态控制点不是通用阶段占位符，而是四个独立任务因果组：

| 控制点 | 因果 decision group | 本任务检查内容 |
|---|---|---|
| `np.cf.classify_port_scope_delta` | classify_live_dependency_change | 消费实时 authority，识别变化只在端口运行所有权 |
| `np.cf.revise_runtime_owner` | revise_affected_runtime_state | 停止冲突服务、保持公开 8080、让 Nginx 成为最终 owner |
| `np.cf.preserve_valid_static_scope` | preserve_unaffected_configuration_and_content | 保留已经正确的配置和静态内容，不做过度失效 |
| `np.cf.reverify_runtime_closure` | reverify_post_resolution_closure | 变更后重新验证 HTTP、404、日志、语法和 lineage 闭包 |

质量 preflight 实测：

- canonical：24/24 通过；
- 非规范等价解：24/24 通过；
- `wrong-authority-receipt`：只杀死预期的 authority/closure 点；
- `rewrite-claimed-preserved-config`：只杀死配置保留与 lineage 点；
- `omit-preserved-artifact`：杀死保留边界声明点；
- canonical、等价解和三个反例使用同一 verifier bundle digest；
- Case IR 与 score plan schema、point-id 对齐、技术晋级门禁均通过。

当前不能写入 registry：`simulation_only.json` 明确记录早期 review/approval 是模拟证据，必须由独立人工重新审查并替换 approval。除此之外，正式论文校准所需 5 模型、3 家族、3 次重复和 40 个执行 mutation 也尚未完成。

## 6. 流水线修复

原 `oracle-all` 会让所有成功 Oracle 容器保持运行，直到后续 `verify-all`。同一 `secure-release` family 的两个实例发布相同宿主机端口，第二个实例因此报 `18080 already allocated`。

新增 `validate-all` 命令，以每个正式 case 任务为生命周期执行 `Oracle -> isolated verifier -> compose cleanup`，再进入下一个任务。它保留了原命令用于单实例调试，同时消除了批量正式验证中的跨实例端口竞争。本次 8/8 完整验证就是使用该命令生成。

## 7. 当前发布决定

`cases/registry.json` 本次不新增任务。严格筛选后的正式新增数为 0；这是门禁正确工作的结果，不是遗漏。

后续只有两类工作可继续：

1. 对 `nginx-live-port-conflict` 做独立人工 source-fidelity/review/approval，完成正式 calibration 后再晋级；
2. 对四条 SWE 重建队列逐条设计不同的 Case IR、事件政策、运行包、语义点、因果控制组、等价解和局部反例，不能复用通用模板批量晋级。

