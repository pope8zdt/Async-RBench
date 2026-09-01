# Track A 冻结主实验：最小冻结案例集 + 测评框架实验设计

> 状态：**设计就绪、实施自测通过；合同尚未冻结，故 test 头条暂不可产出。**
> 本文给出「合同冻结后**立刻**可以计算的」正式实验。它把三项已拍板的统计决定固化进测评框架：
> **① 头条宏平均单位 = 8 个 case family 等权（实现字段为 `primary_event_theme`）；② 收窄分母（不足量 family 剔除并上报）；③ 不配平 composition。**
>
> 与 `实验设计.md` 的关系：那篇是覆盖策略/诊断/消融的伞形方案；本篇只约束 **Track A 正式主结果**所需的最小冻结案例集与评分框架。

---

## 1. 一句话

冻结数据集 = **201 个注册实例**（2026-09-01 冻结：calibration 82 / development 30 / test 89）。Track A 头条指标 = **Async Dynamic Control Score**。头条宏平均单位 = **8 个 case family 等权**（实现字段为 `primary_event_theme`；family 内先做 case 平衡，再做 family 间平衡）。test 分母按 **每个 family 至少 `minimum_theme_test_instances=3` 个已评分实例**收窄；不足量 family 从头条剔除、**单独上报**。**不重配平**数据集组成。

合同当前 `9.1.0-dev`（status=`development`）、dataset `pre_calibration_locked`、校准审计仍有缺口（仅 1 模型试点）→ 冻结门禁（P0-1）**正确拒绝**。因此本文的「最小冻结实验」是**前瞻性设计**：评分框架已实现并单测锁定，一旦合同冻结并补齐校准审计，即可用同一套 `aggregate_reports` 生成正式头条。

---

## 2. 最小冻结案例集

来源：`cases/registry.json`（200 个注册 case_id，201 个实例）。`case_family` 指 8 个 `primary_event_theme` 分类；`case_id` 是某个 family 下的注册 case 单元；`instance_id` 是该 case 下不可变的协议包。**只有 registry 里登记的 case/instance 是官方**。`case_families` 是 schema v2 遗留字段名，其条目实际是注册 case。

### 2.1 分裂（冻结 2026-09-01）

| split | 实例数 | 用途 |
|---|---:|---|
| calibration | 82 | verifier / 协议校准；**永不进入头条** |
| development | 30 | 改 prompt、adapter、实现；**永不进入头条** |
| test | 89 | 合同冻结后**唯一**进入头条的分裂 |
| **合计** | **201** | |

### 2.2 8 个 case family（实现字段：`primary_event_theme`）实例数

| primary event theme | all | test | calibration | development |
|---|---:|---:|---:|---:|
| delayed_authoritative_result | 90 | 51 | 27 | 12 |
| task_scope_or_dependency_change | 39 | 10 | 21 | 8 |
| partial_then_complete_result | 24 | 11 | 9 | 4 |
| late_or_out_of_order_superseded_result | 22 | 8 | 12 | 2 |
| straggler_under_resource_pressure | 10 | 4 | 5 | 1 |
| child_failure_or_implicit_error | 6 | 4 | 0 | 2 |
| conflicting_valid_results | 6 | **0** | 6 | 0 |
| duplicate_or_replayed_completion | 4 | **1** | 2 | 1 |
| **合计** | **201** | **89** | **82** | **30** |

### 2.3 `case_id_policy.maximum_single_case_fraction=0.2` 的澄清

- 该上限是**注册 case_id** 层面的重复/集中度护栏：单个 case_id 最大实例数 = 2（1.0%），**全部满足 ≤0.2**。
- `delayed_authoritative_result` 本身就是一个 case family，其 90/201 = **44.8%** 说明 family composition 不均衡；这不受 case_id 集中度护栏约束，而由「case family 等权」聚合消化。
- 结论：**无 0.2 冲突**。`case_id` 是注册单元，`case_family` 是 8 个分类和头条宏平均单元；两者不可混称。

---

## 3. 测评框架（已实现并单测）

### 3.1 头条宏平均：`_theme_macro`（case family 等权，保留旧函数名）

- **family 内平衡**：某 case family 下，先对每个 instance 的重复观测求均值，再对每个 case_id 的 instance 均值求均值 → 该 family 的 case 平衡分。
- **family 间平衡**：每个满足覆盖门槛的 family 各计 1 票，头条 = kept-family 分数的均值。
- 效果：`delayed_authoritative_result` 在当前 6 个 kept family 中只占 **1 票（1/6）**，不再因 51 个 test 实例（57.3% of test）支配头条。这就是 case family 等权。

### 3.2 收窄分母：`minimum_theme_test_instances=3`（用户决定 ②）

- **规则**：某 case family 在对应模式下**已评分的实例数** < 阈值 → 从头条剔除；兼容字段 `dropped_dynamic_themes` 记录其分数，`dynamic_theme_coverage` 反映 family 保留比例。
- **test 分裂实际结果**（`aggregate_reports` on the real 89 test instances）：

| 状态 | theme | test 实例数 |
|---|---|---:|
| KEEP | delayed_authoritative_result | 51 |
| KEEP | partial_then_complete_result | 11 |
| KEEP | task_scope_or_dependency_change | 10 |
| KEEP | late_or_out_of_order_superseded_result | 8 |
| KEEP | child_failure_or_implicit_error | 4 |
| KEEP | straggler_under_resource_pressure | 4 |
| **DROP** | duplicate_or_replayed_completion | **1**（单一实例 → 方差不可用） |
| **ABSENT** | conflicting_valid_results | **0**（test 无任何实例） |

- **保持 6 / 已评分 7 = 85.7% theme 覆盖**；剔除 `duplicate_or_replayed_completion`，`conflicting_valid_results` 在 test 中**无覆盖**（应单独标注为 uncovered，而非 dropped）。
- 单调 theme（只有一个实例）的剔除使头条方差更稳健；剔除的 theme 必须**始终上报**，杜绝「静默丢分母」。

### 3.3 不配平（用户决定 ③）

- 不把 2.2 的 case family 组成强制配平到等量实例。`delayed` family 的 plurality 仅通过 family 等权处理，数据集组成保持冻结原样。
- 因此**不存在**「调整样例组成来均衡 family」的步骤；这也意味着 test 分裂的覆盖损失（dup dropped / conflict absent）是**可接受且必须报告**的，而非用补样消除。

### 3.4 其余框架要素（已实现/已在位）

| 要素 | 实现 |
|---|---|
| 配对效应 | `_matched_mode_effect`：同 (case, instance, repeat, seed, seed…) 的 Linear/Async 配对,`_pair_key` 保证唯一 |
| 严格 `pass^k` | C(c,k)/C(n,k) |
| bootstrap 多重性 | 先预聚合到 per-case-family / per-case-id 值再重采样 |
| `_dynamic`/`_dt` 严格、`_semantic` 回退 | 线性基线语义、async 动态不回退到语义 |
| split 硬失败 | 官方记录 split 必须是 `test`；跨 split 泄漏判 hard-fail |
| 官方分离 | 只有 `split=="test"` 且 `leaderboard_eligible` 进入 headline |
| 原子 token 预算 | `reserve`(检查+预留同锁) + `settle`(释放/结算)，并发 child 不越界 |
| 可见性隔离 | 参与者轨迹不含 `result_kind`/`event_assets`/`observer_command`/`validator_command`/`check_id` 等私有字段 |

---

## 4. 冻结门禁（P0-1，已实现 `validate_frozen_release`）

入库 `evaluation_contract.json` 冻结版本，**同时**满足：

| 条件 | 当前值 | 是否满足 |
|---|---|---|
| `contract.status == "frozen"` | `development` | ❌ |
| `contract.version` 非 `-dev` | `9.1.0-dev` | ❌ |
| `dataset_policy.status ∈ {post_calibration_locked,…}` | `pre_calibration_locked` | ❌ |
| `calibration_audit.total_gaps == 0` | 有缺口（1 模型试点） | ❌ |
| 冻结面板 `len(model_panel) ≥ minimum_pilot_models` | 1 < 5 | ❌ |
| 冻结面板 `≥ minimum_model_families` | 1 < 3 | ❌ |

**结论：合同**不得**冻结、test 头条**不得**产出。门禁 fail-closed：证书未冻结时 `--release` 校验直接拒绝。

冻结前必须完成：≥5 个模型、≥3 个 model family、每模型每模式≥3 次重复、每 case≥40 个 executed mutants、mutation kill ≥0.95、critical ≥1.0、非退化点比例≥0.8、|φ|≤0.8、mean/single-model dynamic X 未饱和（≤0.85 / ≤0.98）。

---

## 5. 冻结后正式实验矩阵

### 5.1 主结果（Track A）

- 因变量：Async Dynamic Control Score（头条）、Dynamic Success Rate、Critical Dynamic Points All-Pass、Semantic Task Score（Linear/Async）、配对语义下降、DTScore、pass¹/²/³、token/墙钟/子智能体/无效工作比。
- 自变量：model × guidance；`linear` 与 `async` 同实例配对。
- 统计：以 case family 等权头条、bootstrap CI（multiplicity 校正）、配对均值差±CI。

### 5.2 敏感性（用于正文讨论，非 component ablation）

- **leave-one-family-out**：逐 case family 剔除后重算头条与排名；实现仍按 `primary_event_theme` 字段选择，且在收窄后的 kept-family 集合上执行。
- DTScore 权重 `0.6D+0.4S` / `0.8D+0.2S` 与单独 D/S。
- relevance weight：uniform vs 当前分级权重。
- 重复次数下的排名与 CI 稳定性。

### 5.3 诊断（不进入头条）

- 第二组控制器策略（Model-Native / Greedy / Wait-All / Version-Aware / Oracle）——只作为策略基线，报告全量 + 预注册适用子集。
- 第三组案例条件化反事实（no-event / canonical-order / perfect-worker / dependency-oracle / resource-relaxation）。
- Benchmark Design 消融（Semantic-Only / Process-Only / Point-Micro / Unpaired）——见 `实验设计.md` §6。

---

## 6. 局限与显式声明

1. **合同未冻结**，本文是前瞻设计；「test 头条 6/7 theme 覆盖」是**当前分裂下的组成事实**，不等于已产生分数。
2. `conflicting_valid_results` family 在 test 分裂**零实例** → 头条完全不覆盖该 family；这是**组成性缺口**（非收窄所致），需在论文 valid-claims 里显式声明，而非自动混入 dropped。
3. `duplicate_or_replayed_completion` family 的 test 仅 1 实例 → 收窄剔除；其 2 个 calibration 实例可用于诊断组，**不进 test 头条**。
4. `case_id_policy` 的 0.2 上限按**注册 case_id** 判；case family 组成不均衡由 family 等权聚合处理。两层不可混称。
5. 「不配平」意味着 test 分裂的 family coverage < 100% 是**刻意的**，不作为缺陷修复；上升为论文 claim 时需报告兼容字段 `dynamic_theme_coverage` 与 `dropped_dynamic_themes`。
