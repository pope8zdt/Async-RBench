# Paper-Eval-80 case 清理与重新分布设计

日期：2026-09-04

基线：`origin/main@48d98c2f21aa518f5fe840a683ee126200fbe989`

目标分支：`codex/paper-eval-80-redesign`

## 1. 决策摘要

本次调整采用“双层分布”模型：

1. 保留仓库已有 `calibration`、`development`、`test` split 的历史含义，不把曾用于开发或校准的 case 重新包装成全新的 held-out test。
2. 新增并冻结独立的 `Paper-Eval-80` 评测清单，作为论文主实验的 80-case cohort。
3. Paper-Eval-80 固定为 **61 个保留并修复的现有 case + 19 个新建 case**。
4. `gaia2-stockholm-moveout` 不补契约、不迁移，必须从 case 目录、注册表、迁移清单、测试特例和论文选择物中全面移除。
5. 旧 case 只保留进入 Paper-Eval-80 且达到统一质量门槛的部分；未入选且仍处于旧刺激或旧契约状态的 case 从正式仓库表面移除。

该方案将“历史数据划分”和“论文评测样本”分开表达，避免测试集标签失真，同时让 GitHub 上正式可见的 case、迁移状态和论文清单保持一致。

## 2. 当前问题

远端基线包含 200 个 case 目录、201 个注册实例，历史 split 为 82 个 calibration、30 个 development、89 个 test 实例。已提交的迁移清单仍显示 20 个实例需要 stimulus migration，其中 16 个被选入论文候选集；但对当前 case 文件重新生成审计后会出现 31 个误报。根因是审计器把同一 async schedule 中的普通基线 `result_delivery` 也纳入主题 stimulus 集合，而不是只判断带事件契约的焦点事件及其配套控制事件。

现有 Paper-Eval 草案使用 62+18，但存在三个问题：

- `gaia2-stockholm-moveout` 被算作现有样本，却没有完整事件契约；现在已决定全面移除。
- 4 个 legacy case 已经具备完整 v4 事件语义，但旧迁移清单仍把它们标成 `not_declared`；真实需求是 v4→v7 规范化和清单重算，而不是重新发明事件契约。
- GitHub 正式 case 表面仍混有未入选、未迁移的旧 case，论文 cohort 也尚未作为机器可读的冻结产物进入仓库。

## 3. 目标状态

### 3.1 Paper-Eval-80 配额

每个事件主题 10 个 case，总计 80 个；总体难度为 40 Hard / 40 Medium。

| 事件主题 | 现有 | 新建 | 最终 |
|---|---:|---:|---:|
| `child_failure_or_implicit_error` | 6 | 4 | 10 |
| `conflicting_valid_results` | 6 | 4 | 10 |
| `delayed_authoritative_result` | 10 | 0 | 10 |
| `duplicate_or_replayed_completion` | 4 | 6 | 10 |
| `late_or_out_of_order_superseded_result` | 10 | 0 | 10 |
| `partial_then_complete_result` | 10 | 0 | 10 |
| `straggler_under_resource_pressure` | 6 | 4 | 10 |
| `task_scope_or_dependency_change` | 9 | 1 | 10 |
| **总计** | **61** | **19** | **80** |

来源分布固定为：

| 来源 | 现有 61 | 新建 19 | 最终 80 |
|---|---:|---:|---:|
| MultiAgentBench | 34 | 0 | 34 |
| OSWorld | 8 | 8 | 16 |
| SWE-bench | 9 | 6 | 15 |
| TerminalBench | 10 | 5 | 15 |
| GAIA2 | 0 | 0 | 0 |

新增的第 19 个 gap 为 `TerminalBench / Hard / task_scope_or_dependency_change`，用于替代被移除的 GAIA2 样本。其 source task、trajectory 和最终 case ID 必须在构造前冻结，并通过与其他 79 个样本相同的去重和质量门槛。

### 3.2 现有 61 个的状态

现有 61 个由原 62 个清单移除 `gaia2-stockholm-moveout` 得到，分为：

- 41 个 `ready`：重新执行统一 release gate 后直接保留。
- 16 个 `migration_audit_false_positive`：真实 stimulus、事件契约、动态点计划和 verifier 已迁移；保留现有内容，修正审计器只分类焦点事件与配套控制事件，并重新执行主题级测试。
- 4 个 `normalization_required`：事件语义已完整，只需把 v4 契约规范化为 v7 动态点计划与私有镜像，并由真实文件重新生成迁移状态。

4 个规范化对象为：

- `git-conflict-and-cleanup-closure`
- `scheduler-selective-replan`
- `distributed-model-runtime`
- `secure-release` 的 `seed-1`

## 4. 删除边界

删除仅针对 GitHub 仓库内容，不删除主工作区中被忽略的 `candidate_cases/`、`candidate_instances/` 或其他本地实验产物。

### 4.1 全面移除 GAIA2

对 `gaia2-stockholm-moveout` 执行全链路删除：

- 删除 `cases/gaia2-stockholm-moveout/` 全目录。
- 删除注册表中的 case/instance 记录。
- 删除迁移 manifest 中对应记录。
- 删除测试、脚本和文档中以该 case ID 为对象的特例、豁免和断言。
- 从 Paper-Eval 选择文件及统计中移除。
- 保留仍被其他数据流程使用的通用 GAIA 导入/构造能力；只有在证明没有任何调用者后才删除通用代码。

### 4.2 移除未入选的旧 case

以下仍需要 stimulus migration、但未进入现有 61 的旧 case 目录从正式仓库表面移除：

- `mab-dependency-unblock-3005dbb57f`
- `mab-dependency-unblock-8d29bb0513`
- `swe-dependency-unblock-8902c7f431`
- `swe-late-constraint-7ce47cda27`

以下未入选且仍是旧契约形态的 legacy case 也移除：

- `data-recovery-service`
- `swe-bench-selective-patch`

`secure-release` 目录保留，但删除未入选的第二实例 `tracebench-git-recovery-late-authority-001`，只保留并规范化 `seed-1`。

因此，删除规模为 **7 个 case 目录 + 1 个额外 instance**。在新增 19 个 case 后，正式仓库预期为 **212 个 case 目录、212 个注册实例**。该数字是实现验收约束，不是通过手工编辑统计得到的展示值。

## 5. 迁移与新建规则

### 5.1 复验 16 个已迁移 case

被旧清单误标、需要保留并复验的 16 个 case 为：

- `mab-dependency-unblock-031ed6f5bc`
- `mab-dependency-unblock-09f3ab60d7`
- `mab-dependency-unblock-0daa930906`
- `mab-dependency-unblock-0de81e81ac`
- `mab-dependency-unblock-2cf6576816`
- `mab-dependency-unblock-720c69400a`
- `mab-dependency-unblock-940b9b95f0`
- `mab-dependency-unblock-94c68e7815`
- `mab-dependency-unblock-9739b40e89`
- `mab-late-constraint-203f5009fd`
- `mab-late-test-evidence-4c6c77884e`
- `mab-late-test-evidence-60efb2bdee`
- `mab-late-test-evidence-7d09ace3d3`
- `swe-dependency-unblock-3361c7af50`
- `swe-late-constraint-3950516755`
- `tbn-late-test-evidence-9685a54f22`

这 16 个 case 不重新构造。审计器必须从 `control_flow_checks.json.event_contracts[*].event_id` 定位焦点事件，再把该焦点事件及显式关联的 replay/deadline/resource 控制事件作为主题 stimulus；普通 upstream/baseline delivery 不参与主题兼容性判断。复验仍必须证明事件注入、契约字段、动态点计划、私有镜像、verifier 和负向 mutation 对齐同一语义。

### 5.2 新建 19 个 gap case

原 18 个 gap 的主题构成为 Conflict 4、Child failure 4、Duplicate/replay 6、Straggler 4；继续沿用已选定的 OSWorld 8、SWE-bench 6、TerminalBench 4 个 source 候选。

第 19 个 gap 增加为：

- 主题：`task_scope_or_dependency_change`
- 来源：TerminalBench
- 难度：Hard
- 暂定 ID：`tbn-task-scope-dependency-change-pe80-01`
- 约束：至少 3 个 workstream、2 条依赖边；事件必须在 provisional artifact 后改变任务范围或依赖图；保留不受影响的成果，只重规划受影响分支。

暂定 ID 只用于设计定位。实施时必须先冻结唯一 source task、版本、资产和 trajectory digest，再生成最终 ID 与 provenance。

## 6. 每个正式 case 的统一事件契约

每个保留、迁移或新建 case 都必须具备以下可执行字段，并在公开 control-flow checks 与私有镜像之间一致：

- 唯一 `event_id` 和 `primary_event_theme`
- `required_changes`
- `required_preservation`
- `forbidden_changes`
- `closure_checks`
- `expected_disposition`
- `event_status`

同时必须显式记录 stimulus type、trigger、provisional predicate、authority/generation/lease 绑定和事件注入窗口。Async 与 Linear 轨道必须调用同一语义 verifier；允许执行路径不同，不允许通过不同验收标准制造分数差异。

每个 case 至少满足：

1. source task、版本、资产和 trajectory digest 冻结。
2. 80 个样本之间 source task 唯一；如因 legacy/composite 不能做到，必须显式登记 source cluster，并提供“一源一例”敏感性结果。
3. source-native tests、hidden verifier、equivalence solution、Docker oracle 和统一 release gate 全通过。
4. Medium 至少杀死 2 个负向 mutation。
5. Hard 至少覆盖 3 个 workstream、2 条依赖边，并杀死 2 个不同 failure family 的 mutation。
6. 关键动态点覆盖 dispatch、provisional、event、reconcile/closure 四个阶段。

## 7. 冻结产物与可复现性

仓库新增或更新以下机器可读产物：

- `paper-eval-80-existing-61.csv`：61 个保留 case、instance、原始 split、来源、主题、难度和 readiness。
- `paper-eval-80-gap-19.csv`：19 个 gap 的 source binding、主题、难度和构造状态。
- Paper-Eval-80 总 manifest：冻结最终 80 个 case 的唯一顺序、provenance、source digest、case digest 和状态。
- 更新后的事件迁移 manifest：由 case 实际文件生成，不允许人工保留已失真的 `not_declared` 状态。
- 选择说明文档：解释 61+19、0 GAIA2、历史 split 与论文 cohort 的区别。

现有选择 salt 保持不变：

```text
sha256("async-rbench-paper-eval-80-v1|" + case_id)
```

最终运行顺序继续使用独立 salt：

```text
sha256("async-rbench-paper-eval-80-run-order-v1|" + case_id)
```

删除 GAIA2 并加入第 19 个 gap 后，必须对 80 个最终 case 重新计算确定性顺序并冻结清单 digest。

## 8. 防止状态漂移的实现约束

迁移状态和 Paper-Eval 统计必须通过生成器从 case、注册表和选择 manifest 计算，而不是在多个 Markdown/JSON/CSV 中分别手工维护。生成器需要在校验模式下检测工作树产物是否过期，并由测试阻止以下回归：

- 已删除 case 再次出现在注册表、迁移清单、测试或文档中。
- `matches_frozen_stimulus` 与实际 stimulus/contract 不一致。
- 80 集数量、主题、难度、来源或运行顺序发生未审阅变化。
- 同一 case/instance/source task 重复进入 80 集。
- Linear 与 Async 使用不同的语义 verifier。

## 9. 实施顺序与验证

实施采用测试先行，按以下顺序推进：

1. 增加仓库表面与 Paper-Eval 配额测试，使旧 62+18、GAIA2 引用和旧 migration 状态先失败。
2. 全面删除 GAIA2、6 个未入选旧目录和 `secure-release` 的额外实例；同步注册表和引用。
3. 规范化 4 个 v4 legacy case。
4. 修正迁移审计器的焦点事件分类，并复验 16 个已迁移 case，不重写其已通过的事件语义。
5. 冻结并构造 19 个 gap case。
6. 生成 61、19、80 和 migration 产物，冻结 digest。
7. 对全部 case 运行静态完整性审计、source-native checks、负向 mutation、Docker oracle 和统一 release gate。
8. 运行完整 pytest；确认工作树只包含本设计范围内的变更。
9. 经审阅后提交并推送 GitHub 分支；不直接覆盖远端 `main`。

最少验收断言包括：

- 仓库中不存在字符串或路径 `gaia2-stockholm-moveout`。
- case 目录数和注册实例数均为 212。
- Paper-Eval manifest 恰好 80 条，分解为 61 existing + 19 new。
- 8 个主题各 10 条，难度恰好 40 Hard / 40 Medium。
- 来源恰好 MAB 34、OSWorld 16、SWE 15、TBN 15、GAIA2 0。
- 61 个 existing 全部为 `ready`，19 个 new 全部通过同一 release gate。
- manifest 生成器重复运行不产生 diff。

## 10. 非目标

- 不重写已有实验结果来伪造新的 held-out test 历史。
- 不清理或删除被 Git 忽略的本地候选池与运行输出。
- 不因为移除单个 GAIA2 case 而自动移除所有通用 GAIA 支持代码。
- 不在 case 语义尚未验证时仅通过改标签、改计数完成迁移。

## 11. 风险与控制

- **来源相关性风险**：legacy/composite case 可能共享底层 TerminalBench source。通过 source-cluster 登记、cluster bootstrap 和“一源一例”敏感性分析控制。
- **大批量 case 漂移风险**：通过生成器、冻结 digest 和精确配额测试控制。
- **迁移只改声明、不改行为的风险**：通过真实 stimulus、统一 verifier、负向 mutation 和 Docker oracle 共同控制。
- **误删本地实验数据风险**：所有实施在独立 worktree 中完成，删除目标只允许是版本库内已确认的精确路径。
- **论文 split 表述风险**：论文主表称为 `Paper-Eval-80 cohort`，原始 split 作为 provenance 字段保留，不宣称所有 80 个都是从未使用的 test。
