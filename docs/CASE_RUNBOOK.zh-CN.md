# Async-RBench Case 运行说明书

本文面向获得私有仓库权限的实验人员，说明如何从全新环境拉取 Async-RBench、验证安装，并运行一个注册 case 的 Linear/Async 配对实验。

## 1. 保密与实验边界

本仓库包含 private case、事件真值、hidden verifier 和 held-out test。获得仓库权限不代表可以把这些内容提供给被测 Agent，亦不得公开仓库、公开 fork、上传到网盘或将 private 文件复制到 participant workspace。

在负责人明确启动正式总实验前：

- 只运行 `calibration` 或 `development` split；
- 不查看或运行 `test` split；
- 不根据 test 内容修改 prompt、adapter、评分阈值或 verifier；
- 所有试运行均标记为 development/pilot，不作为论文头条结果。

正式注册范围以 `cases/registry.json` 为准。case 目录存在但未登记的内容不构成正式实例。

术语约定：**case family 指 8 个 `primary_event_theme` 分类**；`case_id` 是某个分类下的注册 case，`instance_id` 是该 case 的不可变实例。`registry.json` 中的 `case_families` 是为兼容 schema v2 保留的旧字段名，其中每一项实际是注册 case，不能再按论文概念解释为 family。

### 1.1 术语对照：论文概念 vs 兼容字段

论文和正式统计用「case family / case / instance」三个层次，但框架代码里并存着几组历史字段名。为避免把遗留名误读成新概念，对照如下：

| 论文概念 | 兼容 / 实现字段 | 说明 |
|---|---|---|
| case family（8 个事件分类） | 每个注册 case 上的 `primary_event_theme` | 头条宏平均单位；聚合上报用 `theme_*` 前缀 |
| 「case family 等权头条」 | `headline_macro_unit="event_theme"` + `theme_dynamic_control_scores` 等 | `aggregate` 输出的主题等权结果，非实例加权 |
| 收窄分母（不足量 family 剔除） | `minimum_theme_test_instances`（阈值）<br>`dropped_dynamic_themes`（剔除主题及分）<br>`dynamic_theme_coverage`（保留比例）<br>`theme_instance_count_minimum` | 已评分实例数少于阈值 → 从头条剔除并单独上报 |
| case_id（注册单元） | `case_id` | 集中度护栏按此判；`case_families` 的元素其实是注册 case |
| case_id 集中度护栏 | `case_id_policy.maximum_single_case_fraction=0.2`（旧名 `family_policy.maximum_single_family_fraction`） | 按注册 case_id 判，**不是**按 theme 判 |
| instance_id（不可变实例） | `instance_id` | 运行键格式 `case_id::instance_id` |
| generation / source family（来源归属） | `legacy_family_policy`（仅 provenance） | 只是案例来源标记，**永不**作为 async 分类 |

一条判别准则：论文里说 **family 是 8 个分类**；代码里凡以 `family_*` 命名的历史字段，大多指的是注册 case、来源或以 `case_id` 为单位的护栏。看到 `family_*` / `case_families` 时，先判它到底绑定的是哪一层，再按上表换算。

## 2. 环境要求

推荐环境：

- Git；
- Python 3.11 或更新版本；
- Windows PowerShell 7；
- Docker Desktop，使用 Linux container engine；
- 至少 30 GB 可用磁盘空间，用于容器镜像和运行产物；
- 一个与配置文件匹配、支持 function/tool calling 的模型 API。

OSWorld、MARBLE 和 source-native SWE 路径有额外环境要求，见本文第 10 节。普通注册 case 的容器化配对运行不要求下载整个 `upstream/` 目录。

## 3. 拉取私有仓库

确保 GitHub 账号已经被加入仓库，然后执行：

```powershell
git clone https://github.com/pope8zdt/Async-RBench.git
Set-Location Async-RBench
git rev-parse HEAD
```

记录打印出的 commit SHA。一次实验中的所有参与者必须使用同一 SHA；实验开始后不要直接在工作目录修改 case、合同或模型配置。

如果 Windows 报路径过长，请先在管理员 PowerShell 中执行：

```powershell
git config --system core.longpaths true
```

## 4. 创建环境并安装

Windows PowerShell：

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

Linux/macOS：

```bash
python3.11 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -e ".[test]"
```

确认 Docker Linux engine 已启动：

```powershell
docker info
```

## 5. 无付费预检

先运行仓库静态校验和框架测试：

```powershell
python -m async_rbench.cli validate
python -m pytest -q
```

这里不使用 `--release`。当前评测合同仍是 development，release gate 正确拒绝正式冻结并不代表普通 case 运行失败。

如上述任一命令失败，不要启动付费模型实验。保存完整错误输出并报告 commit SHA、Python 版本、Docker 版本和操作系统。

### 5.1 关于克隆测试中的 skip 项

仓库有意不随库发布大体积作者本地输入（`upstream/*` 上游源码树、
`candidate_cases/`、`candidate_instances/` 生产数据、`artifacts/*` 运行时产物）。
依赖这些资源的测试通过 `tests/author_local.py` 守卫：资源缺失时以明确原因跳过
（`author-local resource is not part of the repository checkout: ...`），因此
**干净克隆上 pytest 应当通过且只出现 skip，不出现 failed/error**；在作者机器上
这些资源齐全，同一批测试全部正常执行。克隆基线：482 collected 左右，0 失败，
skip 数为上述作者本地测试之和。若克隆上出现 failed/error，请报告 commit SHA。

## 6. 选择注册实例

打开 `cases/registry.json`，选择负责人分配的 `calibration` 或 `development` 实例。运行时实例键格式为：

```text
case_id::instance_id
```

建议第一次使用已通过完整 release gate 的 calibration smoke：

```text
secure-release::seed-1
```

不要自行选择 test 实例。四人最小验证实验的分工应以负责人发放的实例清单为准。

## 7. 配置模型凭据

版本化模型配置位于 `configs/model-profiles/`。真实凭据只能放在当前进程的环境变量里，不能写入仓库。

DeepSeek 示例：

```powershell
$env:ASYNC_RBENCH_DEEPSEEK_KEY = Read-Host "DeepSeek API key" -MaskInput
```

OpenAI-compatible 示例：

```powershell
$env:OPENAI_API_KEY = Read-Host "API key" -MaskInput
```

如果需要自定义 endpoint 或模型 ID，把 `configs/model-profiles/reference-config.example.yaml` 复制到被 Git 忽略的 `configs/local/`，再修改副本。不要修改共享版本化 profile。

## 8. 运行一个 Linear/Async 配对 case

统一入口是根目录的 `run_case.ps1`：

```powershell
.\run_case.ps1 `
  -Instance "secure-release::seed-1" `
  -Config "configs/model-profiles/deepseek-v4-pro.yaml" `
  -Repetitions 1 `
  -Seed 2026
```

脚本按顺序执行：

1. 仓库校验；
2. Docker 检查；
3. 生成不可变 manifest；
4. conformance；
5. Linear/Async 配对 episode；
6. 聚合；
7. run audit。

默认输出目录：

```text
artifacts/experiments/manual-<case>-<timestamp>/
├── manifest.json
├── runs/
├── results.json
├── run-audit.json
└── live.log
```

`artifacts/` 已被 Git 忽略。不要强制提交实验输出。

## 9. 中断恢复与结果解释

只有明确的基础设施失败可以恢复；模型失败、超时预算耗尽、错误决策和低分都是有效 participant outcome，不能因为分数低而重跑。

恢复同一实验：

```powershell
.\run_case.ps1 `
  -Instance "secure-release::seed-1" `
  -Config "configs/model-profiles/deepseek-v4-pro.yaml" `
  -ExperimentRoot "artifacts/experiments/manual-secure-release-seed-1-YYYYMMDD-HHMMSS" `
  -Resume
```

恢复时必须使用原目录、原 manifest、原模型配置和原 commit。脚本不会生成新 manifest。

完成后至少检查：

- `manifest.json` 中只有分配的实例和预期执行模式；
- `runs/` 中每个计划 episode 都有记录；
- `results.json` 已生成；
- `run-audit.json` 无 digest、配置或 Linear/Async 配对错误；
- `live.log` 中没有未解释的认证、容器或网络错误；
- participant trace 中没有 private truth、hidden check、event schedule 等字段。

## 10. Source-native 路径

仓库中的注册 case bundle 可以完成标准容器化评测。以下 source-native 复核需要额外外部资源，未随 Git 仓库分发：

- OSWorld：`docs/osworld-environment-smoke.md`；
- MARBLE：`docs/marble-native-environment.md`；
- OSWorld 资产工具：`scripts/fetch_osworld_assets.py`；
- MARBLE 环境工具：`scripts/bootstrap_marble_runtime.py`。

`upstream/` 不进入 Git，因为它包含多个独立仓库、缓存和超大数据文件。需要 provenance 或 source-native 重建时，由负责人提供固定 revision/资产清单，或按照对应文档单独获取。

因此，在未包含 `upstream` 的克隆上，`validate` 会**跳过集合级 source lock 校验**：`upstream/<benchmark>/SOURCE_LOCK.json` 不存在时不再判为错误；`asset_copies` 中指向 `upstream/` 的原件比对同样跳过（case 内副本本身照常存在并可运行）。case 自包含的 per-case source-native 锁（`cases/<case>/private/source_lock.json`）不受影响、照常校验。一旦工作区中存在任意一个集合锁（即已下载完整 `upstream/`），校验立即恢复严格：任何缺失或内容不匹配的集合锁、任何与上传原件不一致的资产副本都会使 `validate` 失败——避免把部分下载误当完整源头。

仓库通过 `.gitattributes`（`* text=auto eol=lf`）把文本文件统一为 LF 行尾；`core.autocrlf` 等本地换行设置不会改变克隆出的字节，因此 `source_lock.json` 记录的 provenance 哈希在任何平台、任何克隆上都是一致的。

## 11. 向负责人返回什么

不要手工修改输出。压缩完整实验目录并计算 SHA-256：

```powershell
Compress-Archive `
  -LiteralPath "artifacts/experiments/manual-<case>-<timestamp>" `
  -DestinationPath "manual-<case>-<timestamp>.zip"
Get-FileHash "manual-<case>-<timestamp>.zip" -Algorithm SHA256
```

同时报告：

- Git commit SHA；
- 实例键、repeat、seed 和模型 profile；
- 操作系统、Python 和 Docker 版本；
- 开始/结束时间与时区；
- 所有中断、恢复和基础设施异常；
- ZIP 文件及其 SHA-256。

绝不能发送 API Key，也不要只发送人工整理后的分数表而丢弃原始证据。

### 11.1 每条提交记录的终止分类与论文指标（P1-17/18/19）

每条 episode 得分记录（JSONL 的 `score` 记录）带有：

- `child_terminal_classifications`：每个子任务尝试恰有一类互斥终止
  （`accepted` / `public_rejection` / `private_rejection` / `sealed` /
  `resource_exhausted` / `timeout` / `crash` / `cancel` /
  `infrastructure_failure` / `in_flight`）。`attempt_number` / `retry` 把
  "首次 vs 重试" 作为维度写在每一行上，不另建一套计数器。
- `submission_rejection_rate`：拒绝率；分母只含真正提交过的尝试
  （sealed 提交；预算耗尽、设计超时/崩溃、取消、基础设施失败、未跑完均不计入）。
- `extra_rejection_tokens` / `invalid_redelegation_rate` 等成本指标。

聚合报告（`aggregate` 输出）的每条 leaderboard 项和 `development_summary`
还带有 `paper_metrics`：首次/重试提交数与接受率、平均每个接受提交的 token、
拒绝导致的额外 token、无效再委托率。要引用这些指标请使用聚合输出而非单条记录。

## 12. 常见问题

**`validate --release` 失败是否表示框架不能运行？**

不是。当前合同未冻结，正式 release gate 应当失败。使用普通 `validate` 完成开发/验证实验。

**模型得到 0 分，是否需要重试？**

不需要。只要场景成功构造、记录完整且不是基础设施失败，0 分也是有效结果。

**可以把 Linear 写成 ReAct 吗？**

不可以直接等同。当前合同中的正式执行条件是 `linear` 和 `async`；只有单独实现并声明 ReAct controller 后，才能把它作为 ReAct baseline。

**为什么 clone 后没有完整 `upstream/`？**

它不是标准注册 case 运行的必要内容，而且包含嵌套 Git 历史和超大文件。只有 source-native/provenance 复核需要单独准备。
