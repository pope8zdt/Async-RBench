import Link from 'next/link';
import { ArrowRight } from 'lucide-react';
import { metrics } from '@/lib/content';
import { repositoryUrl, submissionUrl } from '@/lib/repository';
export const metadata = { title: '教程与协议' };
const navigation = [
  ['quickstart', '01 · 快速开始'],
  ['tracks', '02 · 选择赛道'],
  ['track-a', '03 · 接入模型'],
  ['track-b', '04 · Agent 系统预览'],
  ['metrics', '05 · 理解结果'],
  ['submission', '06 · 提交与发布'],
  ['protocol', '07 · 协议与常见问题'],
];
export default function Page() {
  return (
    <div className="page-wrap">
      <div className="page-title">
        <h1>教程与协议</h1>
        <p>
          基于 Async-RBench v11.0.0 的实际入口、冻结合约和 Adapter Protocol
          3.0。
        </p>
      </div>
      <div className="docs-layout">
        <aside className="docs-nav" aria-label="教程目录">
          {navigation.map(([id, title]) => (
            <a key={id} href={'#' + id}>
              {title}
            </a>
          ))}
        </aside>
        <article className="docs-content">
          <section id="quickstart">
            <h2>快速开始</h2>
            <p>
              当前评测环境要求 Windows PowerShell 7、Python 3.11+、Git，以及使用
              Linux engine 的 Docker
              Desktop。你需要先取得评测仓库及相应任务资源的访问权限；网站本身不分发私有测试集。
            </p>
            <p>
              代码与版本说明：
              <a className="text-link" href={repositoryUrl}>
                Async-RBench 主仓库
              </a>
              。本教程对应 v11.0.0。201个高质量任务，完整主题分布见{' '}
              <Link className="text-link" href="/tasks">
                任务库
              </Link>
              。主榜展示主实验结果。
            </p>
            <ol>
              <li>在已有仓库中安装依赖，启动 Docker。</li>
              <li>在“开始评测”中填写模型信息并下载配置。</li>
              <li>把配置放在仓库根目录，在终端设置密钥环境变量。</li>
              <li>
                运行开发试跑；启动器会执行 Linear 和
                Async，并生成结果与审计记录。
              </li>
            </ol>
            <pre>{`# 在仓库根目录执行\npython -m pip install -e ".[test]"\ndocker info\npython -m async_rbench.cli validate\n\n# 变量名应与 model-config.yaml 中的 api_key_env 一致\n$env:MODEL_API_KEY = Read-Host "API key" -MaskInput\n\n.\\run_case.ps1 -Instance "secure-release::seed-1" -Config "model-config.yaml" -Repetitions 1 -Seed 2026`}</pre>
            <p>
              首次运行可能需要准备任务依赖。模型调用由你配置的服务计费；仓库校验本身不调用模型。
            </p>
            <Link className="text-link" href="/evaluate">
              生成模型配置 <ArrowRight size={15} />
            </Link>
          </section>
          <section id="tracks">
            <h2>评测赛道</h2>
            <h3>Track A · 固定 harness 下的模型</h3>
            <p>
              固定参考 API
              scaffold、内核、容器隔离、协议检查、验证器、评分和聚合。参与者配置支持的模型/API
              参数，不能替换编排代码。只有通过所有资格检查的运行才可能进入正式榜单。
            </p>
            <h3>Track B · 完整 Agent 系统（模拟预览）</h3>
            <p>
              规划中的赛道，支持预集成框架和自定义策略组件。当前网站仅提供配置与流程模拟；尚无真实驱动、真实结果或正式上榜资格。现有仓库的自定义
              Adapter 仍属于开发运行。
            </p>
            <p className="doc-label">
              依据：docs/evaluation-tracks.md · docs/adapter-contract.md
            </p>
          </section>
          <section id="track-a">
            <h2>接入模型并运行评测</h2>
            <p>
              参考 scaffold 使用支持 function tools 的 OpenAI-compatible Chat
              Completions API。配置精确的模型
              ID；实验条件不包含固定子模型池。子模型为可选运行配置，留空时使用主模型。Linear
              / Async 配对仍须满足同一评分合约与运行绑定。
            </p>
            <p>
              网页生成器支持独立的子模型服务地址与密钥环境变量。在兼容选项中选择
              token 上限参数名称及是否发送 seed。不同 API
              对参数的支持不同，启动器会在运行前执行提供商预检。
            </p>
            <h3>运行主实验</h3>
            <pre>{`python -m async_rbench.cli validate --release\npython -m async_rbench.main_experiment check --root .\n.\\run_main.ps1 -Config "model-config.yaml" -Repetitions 3 -Seed 2026`}</pre>
            <p>
              主实验使用仓库定义的任务清单。每个模型在 Linear 和 Async 下各重复
              3 次。Calibration、Development、Test
              仅保留为历史登记信息，不用于主实验榜单筛选。清单的选取来源记录在实验配置中。
            </p>
            <h3>中断后恢复</h3>
            <p>
              使用相同配置和已有实验目录，通过启动器的 -ExperimentRoot 与
              -Resume
              参数恢复。清单、配置、运行模式或其他绑定不一致时，启动器会拒绝恢复。
            </p>
            <p className="doc-label">
              依据：REFERENCE_SCAFFOLD.md · run_main.ps1 · run_case.ps1
            </p>
          </section>
          <section id="track-b">
            <h2>预集成框架与自定义组件</h2>
            <p>
              第一版预留 Claude Code、基于 LangGraph 的参考 Agent，以及自定义
              Agent 三个入口。下述接口是平台设计提案，不是当前仓库已提供的可调用
              API。
            </p>
            <ul>
              <li>
                <strong>ModelBackend：</strong>调用模型并记录用量。
              </li>
              <li>
                <strong>AgentPolicy：</strong>决定主 Agent 的下一步动作。
              </li>
              <li>
                <strong>ContextBuilder：</strong>
                组织已释放的信息、记忆和上下文。
              </li>
              <li>
                <strong>DelegationPolicy：</strong>
                选择子任务分配、取消和重试策略。
              </li>
            </ul>
            <p>
              RuntimeDriver 将框架映射到当前 JSONL
              协议。异步结果必须先经过网关释放，再进入主 Agent
              请求；框架不能绕过网关提前读取结果。工作区、隐藏验证和评分仍由内核掌握。
            </p>
            <p>
              Claude Code 支持程序化运行，但这本身不能证明其满足 Async-RBench
              的结果控制要求。真实驱动上线前必须进行协议符合性验证。
            </p>
            <Link className="text-link" href="/evaluate?track=b">
              预览模拟流程 <ArrowRight size={15} />
            </Link>
          </section>
          <section id="metrics">
            <h2>评测指标</h2>
            {metrics.map((m) => (
              <div key={m.name}>
                <h3>
                  {m.name} · {m.full}
                </h3>
                <p>
                  {m.description} 对应字段：<code>{m.key}</code>。
                </p>
              </div>
            ))}
            <p>
              主实验指标先平均每个任务的三次重复，再平均主题内任务，最后对八类主题等权宏平均。网站将原始
              0–1 分数乘以 100 展示，不进行额外加权。缺失或未评分显示“—”，与 0
              分有明确区别。
            </p>
            <p>
              统计直接读取主实验 manifest 绑定的
              score.json，仅纳入主实验任务清单。所有计划运行及主指标齐备后才生成完整得分。覆盖不完整时的暂计值仅汇总已完整评分的任务及其覆盖主题，不能当作完整主实验排名。
            </p>
            <p>
              榜单可切换“配对 BTS”和“DRS”：前者并列展示 Linear BTS 与 Async
              BTS，后者展示 Async
              DRS。详情页提供各主题分数，以及完整配对中有记录的 token
              用量和耗时均值、样本数。
            </p>
            <p>
              网站展示结果快照，没有连接参与者电脑的实时进程状态。“覆盖不完整”不能说明程序仍在运行。材料审核与独立复现需要各自的维护者记录，完整覆盖本身不代表已经审核。
            </p>
            <h3>执行失败与评分失败</h3>
            <p>
              基础设施中断、协议问题、未评分和低分是不同事实。未评分 episode
              不应解释为模型得分 0，也不能通过只挑选成功重试提高成绩。查看完成
              配对完成度、评分进度和主题覆盖后再比较。
            </p>
            <p className="doc-label">
              依据：evaluation_contract.json · async_rbench/main_results.py
            </p>
          </section>
          <section id="submission">
            <h2>提交结果</h2>
            <p>
              评测在参与者电脑上执行。通过主仓库的 GitHub
              表单提交工具生成的公开汇总包，或发起 Pull Request 将其放入
              submissions/entries。维护者单独审核，合并后自动发布。首次提交需要登录
              GitHub。
            </p>
            <ol>
              <li>
                在自己的电脑、授权的评测环境中完成运行，保留
                manifest、结果、配置版本和审计记录。
              </li>
              <li>
                整理允许公开的结果摘要，记录 benchmark
                版本、模型版本、运行配置、种子和重复次数。密钥与原始私有轨迹留在本地。
              </li>
              <li>
                提交结果包。维护者核对固定 harness、主实验任务
                清单摘要、Linear/Async 配对完整性和主题覆盖，并在
                submissions/reviews 生成独立审核记录。
              </li>
              <li>
                审核通过后合并结果，托管平台重新生成榜单。参与者自报、材料已审核、独立复现应分别标注，正式上榜还须满足发布合约。
              </li>
            </ol>
            <pre>{`# 开始实验时记录版本\n$benchmarkCommit = git rev-parse HEAD\n\n# 完成后，将 MY_RUN 替换为实际实验目录\npython -m async_rbench.submissions package --root . --manifest artifacts/experiments/MY_RUN/manifest.json --benchmark-commit $benchmarkCommit\npython -m async_rbench.submissions check --root .`}</pre>
            <p>
              结果包保存到
              submissions/entries/&lt;submissionId&gt;.json。单包检查可使用
              validate --root . --input 文件路径。可选的 --config
              只保存配置文件摘要。相同模型的不同运行可以分别提交。
            </p>
            <h3>维护者审核与发布</h3>
            <pre>{`# 完成材料核查后执行；替换 SUBMISSION_ID 和审核者名称\npython -m async_rbench.submissions review --root . --input submissions/entries/SUBMISSION_ID.json --status materials_reviewed --reviewer YOUR_GITHUB_LOGIN\npython -m async_rbench.submissions check --root .`}</pre>
            <p>
              只有完整覆盖主实验任务
              并有匹配审核的提交进入正式排名。提交包和审核记录合并到主分支后，构建流程会校验、合入榜单并发布。修改成绩后需要重新审核。实际完成独立复现后，才使用
              independently_reproduced，并提供 --evidence-url
              对应的公开复现记录。
            </p>
            <p>
              自动校验检查格式、范围、聚合一致性和摘要；审核权限由仓库的审查和合并流程把关。校验通过不等于成绩已经独立复现。
            </p>
            <a className="text-link" href={submissionUrl}>
              打开 Track A 结果提交表单 <ArrowRight size={15} />
            </a>
            <p>
              内部结果中的 leaderboard 字段不自动等同于网站已验证排名。Track B
              模拟记录没有提交资格。
            </p>
            <h3>本地结果如何判断可信度？</h3>
            <p>
              SHA-256
              用于核对文件是否一致，不能证明分数真实。在参与者控制的电脑上，容器也不能向电脑所有者保密验证器或测试数据。需要隐藏评测材料的任务须另行安排维护者复现；当前官网不把本地自报分数标为独立验证成绩。
            </p>
          </section>
          <section id="protocol">
            <h2>结果交付协议</h2>
            <p>
              协议区分三个关键时点：result_available
              表示网关已释放；adapter_queued 表示 Adapter
              已接收；result_presented
              表示结果实际进入一次已启动的主模型请求。模型看到结果，也不意味着理解或接受。
            </p>
            <p>
              工作区操作通过内核能力接口完成；验证结果由评测端产生，Adapter
              不能自行声明验证真值。官方 Track A 使用固定参考 Adapter。
            </p>
            <h3>运行遇到问题怎么办？</h3>
            <ul>
              <li>
                Docker 连接失败：确认 Docker Desktop 已启动并使用 Linux
                engine，再检查 docker info。
              </li>
              <li>401 / 403：检查密钥环境变量名称、密钥和模型访问权限。</li>
              <li>
                服务商拒绝 max_completion_tokens 或
                seed：调整配置页的兼容选项，重新进行提供商预检。
              </li>
              <li>
                覆盖不足：检查本地结果和失败原因，使用相同配置及实验目录恢复；未评分不按零分处理。
              </li>
              <li>
                导出提示重复尝试：明确本次提交对应的
                manifest；保留历史材料，不按分数挑选重试结果。
              </li>
            </ul>
            <h3>为什么没有原始轨迹下载？</h3>
            <p>
              participant_trace.jsonl 是参与者可见的审计接口；event_source.jsonl
              和 trace.jsonl
              包含评测端私有事实。即便参与者可见的轨迹，也需检查任务内容和凭据后才能向所有访问者公开。当前初版只展示允许的汇总字段。
            </p>
            <h3>如何让网站公开访问？</h3>
            <p>
              官网可以部署到 GitHub Pages 或 Vercel，访问者通过 HTTPS
              链接查看教程、生成配置和浏览结果。评测在各自电脑上运行，网站无需常驻评测服务器。模型调用费用由参与者使用的服务决定。
            </p>
            <h3>点击“开始评测”会发生什么？</h3>
            <p>
              页面生成配置与运行脚本。下载后，在自己的电脑上启动评测，完成后整理结果提交。网页不需要保持打开，托管平台也不接收模型密钥。
            </p>
            <p className="doc-label">
              依据：ADAPTER_PROTOCOL.md · 当前网站实现范围
            </p>
          </section>
        </article>
      </div>
    </div>
  );
}
