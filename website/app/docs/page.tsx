import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { T } from '@/components/preferences';
import { CodeBlock } from '@/components/evaluate-form';
import { repositoryUrl, submissionUrl } from '@/lib/repository';

const navigation = [
  ['quickstart', '快速开始', 'Quickstart'],
  ['tracks', '评测赛道', 'Tracks'],
  ['track-a', '接入模型', 'Connect a model'],
  ['track-b', 'Agent 系统', 'Agent systems'],
  ['metrics', '评测指标', 'Metrics'],
  ['submission', '提交结果', 'Submit results'],
  ['protocol', '协议', 'Protocol'],
];

export default function Page() {
  return (
    <div className="page-wrap">
      <div className="page-title">
        <h1>
          <T zh="教程" en="Docs" />
        </h1>
        <p>
          <T
            zh="从第一次试跑到提交结果。"
            en="From your first run to submitting results."
          />
        </p>
      </div>
      <div className="docs-layout">
        <aside className="docs-nav">
          {navigation.map(([id, zh, en]) => (
            <a key={id} href={'#' + id}>
              <T zh={zh} en={en} />
            </a>
          ))}
        </aside>
        <article className="docs-content">
          <section id="quickstart">
            <h2>
              <T zh="快速开始" en="Quickstart" />
            </h2>
            <p>
              <T
                zh="准备 PowerShell 7、Python 3.11+、Git、Docker Desktop（Linux engine），以及仓库和任务资源的访问权限。"
                en="You need PowerShell 7, Python 3.11+, Git, Docker Desktop (Linux engine), and access to the repository and task resources."
              />
            </p>
            <ol>
              <li>
                <T
                  zh="在仓库根目录安装依赖，启动 Docker。"
                  en="Install dependencies in the repository root and start Docker."
                />
              </li>
              <li>
                <Link className="text-link" href="/evaluate">
                  <T zh="生成配置" en="Generate your config" />
                </Link>
                <T
                  zh="，保存为 model-config.yaml。"
                  en=" and save it as model-config.yaml."
                />
              </li>
              <li>
                <T
                  zh="设置密钥环境变量，然后试跑一个任务。"
                  en="Set your API key environment variable, then try one task."
                />
              </li>
            </ol>
            <CodeBlock
              title="POWERSHELL 7"
              text={`python -m pip install -e ".[test]"
docker info
python -m async_rbench.cli validate

$env:MODEL_API_KEY = Read-Host "API key" -MaskInput
.\\run_case.ps1 -Instance "secure-release::seed-1" -Config "model-config.yaml" -Repetitions 1 -Seed 2026`}
            />
            <p>
              <T
                zh="使用配置中的环境变量名。密钥留在本地，模型调用由所选服务计费。"
                en="Use the variable name in your config. Keys stay local; your provider bills model calls."
              />
            </p>
            <a className="text-link" href={repositoryUrl}>
              <T zh="查看仓库" en="View repository" /> <ArrowRight size={15} />
            </a>
          </section>
          <section id="tracks">
            <h2>
              <T zh="评测赛道" en="Tracks" />
            </h2>
            <p>
              <strong>Track A · </strong>
              <T
                zh="通过模型 API 运行固定参考 harness，配对比较 Linear 与 Async。"
                en="Run model APIs through the fixed reference harness, comparing paired Linear and Async execution."
              />
            </p>
            <p>
              <strong>Track B · </strong>
              <T
                zh="Agent 系统赛道规划中。当前仅为模拟预览，无真实执行、成绩或上榜资格。"
                en="The agent systems track is planned. The current simulation has no real execution, scores or leaderboard eligibility."
              />
            </p>
          </section>
          <section id="track-a">
            <h2>
              <T zh="接入模型" en="Connect a model" />
            </h2>
            <p>
              <T
                zh="使用支持 function tools 的 OpenAI-compatible Chat Completions API，填写精确模型版本。子模型可选，默认使用主模型。"
                en="Use an OpenAI-compatible Chat Completions API with function tools and an exact model version. The optional child model defaults to the main model."
              />
            </p>
            <CodeBlock
              title="POWERSHELL 7"
              text={`python -m async_rbench.cli validate --release
python -m async_rbench.main_experiment check --root .
.\\run_main.ps1 -Config "model-config.yaml" -Repetitions 3 -Seed 2026`}
            />
            <p>
              <T
                zh="主实验按固定清单运行，每种模式重复 3 次。启动器会先检查服务连接。"
                en="The main experiment uses a fixed selection and three repetitions per mode. The launcher checks provider connectivity first."
              />
            </p>
            <details>
              <summary>
                <T zh="兼容选项与恢复运行" en="Provider options & resuming" />
              </summary>
              <p>
                <T
                  zh="配置页支持独立子模型地址、密钥变量、输出长度参数与 seed 开关。Track A 保持参考编排、隔离、验证和评分不变。"
                  en="The configuration form supports a separate child endpoint and key variable, output limit parameters and optional seed. Track A keeps reference orchestration, isolation, validation and scoring fixed."
                />
              </p>
              <p>
                <T
                  zh="恢复时，使用相同配置，并为 run_main.ps1 提供 -ExperimentRoot 和 -Resume。绑定不一致时会拒绝恢复。"
                  en="To resume, keep the same configuration and pass -ExperimentRoot and -Resume to run_main.ps1. Mismatched run bindings are rejected."
                />
              </p>
            </details>
          </section>
          <section id="track-b">
            <h2>
              <T zh="Agent 系统 · 模拟预览" en="Agent systems · Simulation" />
            </h2>
            <p>
              <T
                zh="预览 Claude Code、LangGraph 和自定义 Agent 的配置流程。"
                en="Preview configuration workflows for Claude Code, LangGraph and custom agents."
              />
            </p>
            <details>
              <summary>
                <T zh="接口提案" en="Proposed interfaces" />
              </summary>
              <ul>
                <li>
                  <strong>ModelBackend</strong> ·{' '}
                  <T zh="模型调用与用量" en="Model calls and usage" />
                </li>
                <li>
                  <strong>AgentPolicy</strong> ·{' '}
                  <T zh="主 Agent 决策" en="Main agent decisions" />
                </li>
                <li>
                  <strong>ContextBuilder</strong> ·{' '}
                  <T
                    zh="已释放信息与上下文"
                    en="Released information and context"
                  />
                </li>
                <li>
                  <strong>DelegationPolicy</strong> ·{' '}
                  <T
                    zh="子任务分配、取消与重试"
                    en="Delegation, cancellation and retries"
                  />
                </li>
              </ul>
              <p>
                <T
                  zh="这些是设计提案，尚非可调用 API。真实驱动须通过协议验证；结果释放、工作区与评分仍由内核控制。"
                  en="These are proposals, not callable APIs. Real drivers must pass protocol validation; the kernel retains control of result release, workspaces and scoring."
                />
              </p>
            </details>
            <Link className="text-link" href="/evaluate?track=b">
              <T zh="打开模拟预览" en="Open simulation" />{' '}
              <ArrowRight size={15} />
            </Link>
          </section>
          <section id="metrics">
            <h2>
              <T zh="评测指标" en="Metrics" />
            </h2>
            <p>
              <T
                zh="DRS 视图只展示 DRS，并按分数降序排列。BTS 视图展示两项 BTS 及 Async − Linear 差值，差值越大排名越高。"
                en="The DRS view shows only DRS, highest first. The BTS view shows both BTS scores and their Async − Linear difference, ranked highest first."
              />
            </p>
            <ul>
              <li>
                <strong>Linear BTS</strong> ·{' '}
                <T
                  zh="线性执行中的任务正确性"
                  en="Task correctness under linear execution"
                />
              </li>
              <li>
                <strong>Async BTS</strong> ·{' '}
                <T
                  zh="异步执行中的任务正确性"
                  en="Task correctness under asynchronous execution"
                />
              </li>
              <li>
                <strong>Async DRS</strong> ·{' '}
                <T
                  zh="异步事件中的动态重规划质量"
                  en="Dynamic replanning quality under asynchronous events"
                />
              </li>
            </ul>
            <p>
              <T
                zh="分数以 0–100 展示。覆盖不足时显示暂计值；未评分显示“—”，不等于零分。"
                en="Scores are shown on a 0–100 scale. Incomplete coverage produces provisional values; unscored results show “—”, not zero."
              />
            </p>
            <details>
              <summary>
                <T zh="聚合与结果状态" en="Aggregation & result status" />
              </summary>
              <p>
                <T
                  zh="先平均每个任务的三次重复，再平均主题内任务，最后对八类主题等权宏平均。暂计值只汇总已完整评分的任务及其覆盖主题，不作为完整主实验排名。"
                  en="Average three repetitions per task, then tasks within each theme, then equally across eight themes. Provisional values include only fully scored tasks and covered themes; they are not full main-experiment rankings."
                />
              </p>
              <p>
                <T
                  zh="榜单读取固定主实验 manifest 绑定的评分。覆盖、执行状态与审核状态分别报告；覆盖不足不代表仍在运行，完整覆盖也不代表已审核。"
                  en="The leaderboard reads scores bound to fixed main-experiment manifests. Coverage, execution and review status are reported separately: incomplete coverage does not imply a running process, and full coverage does not imply review."
                />
              </p>
              <p>
                <T
                  zh="详情页提供主题分数，以及完整配对中有记录的 token 和耗时均值、样本数。"
                  en="Result details include theme scores and recorded token and duration averages with sample counts from complete pairs."
                />
              </p>
            </details>
          </section>
          <section id="submission">
            <h2>
              <T zh="提交结果" en="Submit results" />
            </h2>
            <p>
              <T
                zh="开始实验时记录版本，结束后生成公开汇总包。将 MY_RUN 替换为实际实验目录。"
                en="Record the revision when starting the experiment, then package the public summary after completion. Replace MY_RUN with your experiment directory."
              />
            </p>
            <CodeBlock
              title="POWERSHELL 7"
              text={`$benchmarkCommit = git rev-parse HEAD

python -m async_rbench.submissions package --root . --manifest artifacts/experiments/MY_RUN/manifest.json --benchmark-commit $benchmarkCommit
python -m async_rbench.submissions check --root .`}
            />
            <p>
              <T
                zh="通过 GitHub 表单提交 submissions/entries 中生成的 JSON。只提交公开汇总，密钥与私有轨迹留在本地。"
                en="Submit the generated JSON from submissions/entries through the GitHub form. Share only public aggregates; keep keys and private traces local."
              />
            </p>
            <a className="text-link" href={submissionUrl}>
              <T zh="提交 Track A 结果" en="Submit Track A results" />{' '}
              <ArrowRight size={15} />
            </a>
            <details>
              <summary>
                <T zh="审核与发布" en="Review & publication" />
              </summary>
              <p>
                <T
                  zh="提交属于自报结果。正式排名要求完整覆盖和匹配的维护者审核记录；修改成绩后须重新审核。独立复现须另有证据。"
                  en="Submissions are self-reported. Ranked entries require full coverage and a matching maintainer review; score changes require a new review. Independent reproduction requires separate evidence."
                />
              </p>
              <p>
                <T
                  zh="自动校验检查格式与摘要，不能认证成绩或审核者身份。SHA-256 只证明文件一致性；本地容器不能向电脑所有者保密测试材料。"
                  en="Automated checks validate format and digests; they cannot authenticate scores or reviewer identity. SHA-256 proves file consistency only; local containers cannot hide test materials from the host owner."
                />
              </p>
              <p>
                <T
                  zh="维护者完成材料核查后，替换下方提交 ID 与审核者名称并执行。"
                  en="After reviewing the materials, maintainers replace the submission ID and reviewer name below and run:"
                />
              </p>
              <CodeBlock
                title="POWERSHELL 7"
                text={`python -m async_rbench.submissions review --root . --input submissions/entries/SUBMISSION_ID.json --status materials_reviewed --reviewer YOUR_GITHUB_LOGIN
python -m async_rbench.submissions check --root .`}
              />
              <p>
                <T
                  zh="提交包与独立审核记录合并后发布。只有实际复现完成，才能使用 independently_reproduced 并附 --evidence-url。"
                  en="Publication follows merging the package and separate review record. Use independently_reproduced with --evidence-url only after actual reproduction."
                />
              </p>
            </details>
          </section>
          <section id="protocol">
            <h2>
              <T zh="结果交付协议" en="Result delivery protocol" />
            </h2>
            <p>
              <code>result_available → adapter_queued → result_presented</code>
            </p>
            <p>
              <T
                zh="网关释放结果，Adapter 接收，再进入已启动的主模型请求。收到不等于理解。验证与评分由评测内核负责。"
                en="The gateway releases a result, the adapter receives it, then it enters a started main-model request. Receipt does not imply understanding. The evaluation kernel owns validation and scoring."
              />
            </p>
            <details>
              <summary>
                <T zh="排查运行问题" en="Troubleshooting" />
              </summary>
              <ul>
                <li>
                  <T
                    zh="Docker 失败：确认 Linux engine 已启动，检查 docker info。"
                    en="Docker errors: start the Linux engine and check docker info."
                  />
                </li>
                <li>
                  <T
                    zh="401 / 403：检查密钥变量、密钥与模型权限。"
                    en="401 / 403: check the key variable, API key and model access."
                  />
                </li>
                <li>
                  <T
                    zh="参数被拒绝：调整输出长度参数或 seed 开关，再执行预检。"
                    en="Rejected parameters: adjust the output limit parameter or seed toggle, then rerun preflight."
                  />
                </li>
                <li>
                  <T
                    zh="覆盖不足：检查失败原因，以相同配置恢复。重复尝试须明确 manifest，不能按分数挑选。"
                    en="Incomplete coverage: inspect failures and resume with the same configuration. Resolve duplicate attempts by manifest, never by selecting higher scores."
                  />
                </li>
              </ul>
            </details>
            <details>
              <summary>
                <T zh="审计材料" en="Audit materials" />
              </summary>
              <p>
                <T
                  zh="participant_trace.jsonl 是参与者审计接口。event_source.jsonl 和 trace.jsonl 含评测端私有事实。网站只展示允许公开的汇总字段；公开轨迹前须检查任务内容与凭据。"
                  en="participant_trace.jsonl is the participant audit interface. event_source.jsonl and trace.jsonl contain private evaluator facts. The website exposes allowlisted aggregates only; inspect task content and credentials before sharing traces."
                />
              </p>
            </details>
          </section>
        </article>
      </div>
    </div>
  );
}
