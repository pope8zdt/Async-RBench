import {preparePublicSubmission} from './github-static.mjs';

export class SubmissionController {
  constructor(fetcher = globalThis.fetch.bind(globalThis), onChange = () => {}, options = {}) {
    this.fetcher = fetcher;
    this.onChange = onChange;
    this.options = options;
    this.generation = 0;
    this.state = {view:'submit',busy:false,draft:null,entries:[],error:null,fileName:''};
  }
  update(values) { Object.assign(this.state,values); this.onChange(this.state); }
  async setView(view) {
    if (!['submit','community'].includes(view)) return;
    const generation = ++this.generation;
    this.update({view,busy:view==='community',error:null});
    if (view !== 'community') return;
    try {
      const response = await this.fetcher(this.options.staticMode ? this.options.communityUrl : '/api/community');
      if (!response.ok) throw new Error('network');
      const value = await response.json();
      if (!Array.isArray(value.entries) || (this.options.staticMode && value.schema!=='async-rbench-community-board-1')) throw new Error('network');
      if (generation === this.generation) this.update({entries:value.entries,busy:false});
    } catch {
      if (generation === this.generation) this.update({error:'network',busy:false});
    }
  }
  async upload(file) {
    if (!file) return;
    const generation = ++this.generation;
    this.update({view:'submit',busy:true,draft:null,error:null,fileName:file.name});
    if (file.size > 8*1024*1024) { this.update({busy:false,error:'large'}); return; }
    try {
      const raw = await file.text();
      if (generation !== this.generation) return;
      const receipt = JSON.parse(raw);
      if (this.options.staticMode || receipt.schema==='async-rbench-public-submission-1') {
        this.update({draft:preparePublicSubmission(receipt),busy:false});
        return;
      }
      const response = await this.fetcher('/api/prepare',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({receipt})});
      const value = await response.json();
      if (generation !== this.generation) return;
      if (!response.ok) throw new Error('invalid');
      this.update({draft:value,busy:false});
    } catch {
      if (generation === this.generation) this.update({error:'invalid',busy:false,draft:null});
    }
  }
}

const escape = value => String(value ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const bi = (en,zh) => `<span class="i18n" lang="en">${en}</span><span class="i18n" lang="zh">${zh}</span>`;
const root = typeof document !== 'undefined' && document.querySelector('[data-github-submission-root]');
if (root) {
  const app = root.querySelector('#contribution-app');
  const message = root.querySelector('#contribution-message');
  const staticMode = root.dataset.staticMode==='true';
  const controller = new SubmissionController(globalThis.fetch.bind(globalThis),render,{staticMode,communityUrl:root.dataset.communityUrl});
  const instructions = `<details><summary>${bi('Prepare a receipt','准备回执')}</summary>
    <p>${bi('Export from a completed Async run. No evaluation is started.','从已完成的 Async 运行导出，不会启动新的测评。')}</p>
    <pre>python -m async_rbench.submissions export \\
  --run-root runs/my-model \\
  --manifest manifest.json --audit audit.json \\
  --agent "My agent" --model "MODEL_ID" \\
  --organization "My team" \\
  --code-revision FULL_COMMIT_SHA \\
  --output receipt.json

python -m async_rbench.submissions prepare receipt.json --output submission.json</pre>
    <p>${bi('Choose submission.json below. Keep receipt.json private.','下方选择 submission.json。receipt.json 请留作私下审核。')}</p>
    <p>${bi('Use one line in PowerShell. Keep the original run files for private review.','PowerShell 请合并成一行。保留原始运行文件，用于私下审核。')}</p>
  </details>`;
  function picker(state) {
    return `<label class="receipt-picker">${bi(state.draft?'Choose another file':'Choose submission file',state.draft?'更换文件':'选择提交文件')}<input id="receipt-file" type="file" accept=".json,application/json" aria-label="Choose public submission JSON"></label>
      ${state.fileName?`<p class="receipt-name">${escape(state.fileName)}</p>`:''}`;
  }
  function render(state) {
    root.querySelectorAll('[data-view]').forEach(button=>{
      if (button.dataset.view===state.view) button.setAttribute('aria-current','page');
      else button.removeAttribute('aria-current');
    });
    app.setAttribute('aria-busy',String(state.busy));
    message.classList.toggle('error',Boolean(state.error));
    const errors = {
      invalid:bi('Choose the public submission.json file. Prepare it from your original receipt.','请选择从原始回执生成的公开 submission.json 文件。'),
      network:bi('Results could not be loaded. Please try again.','暂时无法载入结果，请重试。'),
      large:bi('Choose a receipt smaller than 8 MB.','请选择小于 8 MB 的回执。')
    };
    message.innerHTML = errors[state.error] || (state.busy ? bi('Checking…','正在检查…') : '');
    if (state.view==='community') {
      app.innerHTML = state.entries.length ? `<div class="community-table"><table><thead><tr>
        <th>${bi('Agent','参评系统')}</th><th>${bi('Model','模型')}</th><th>DRS</th><th>${bi('Success','成功率')}</th><th>${bi('Review','审核')}</th>
        </tr></thead><tbody>${state.entries.map(entry=>`<tr>
          <td>${escape(entry.metadata.agent)}</td><td>${escape(entry.metadata.model)}</td>
          <td class="community-score">${Number(entry.metrics.drs).toFixed(1)}</td><td class="community-score">${Number(entry.metrics.success).toFixed(1)}%</td>
          <td><a href="https://github.com/pope8zdt/Async-RBench/issues/${Number(entry.issue)}" target="_blank" rel="noopener noreferrer">#${Number(entry.issue)} ↗</a></td>
        </tr>`).join('')}</tbody></table></div><p class="community-footer">${bi('Maintainer-reviewed community results.','经维护者审核的社区结果。')} <a href="#leaderboard">${bi('Paper leaderboard →','论文榜单 →')}</a></p>`
        : `<div class="community-empty"><h3>${bi(state.busy?'Loading results…':'No reviewed results yet.',state.busy?'载入结果…':'暂无已审核的社区结果。')}</h3><p>${bi('Community submissions stay separate from the paper results.','社区提交与论文结果独立展示。')}</p><a href="#leaderboard">${bi('View paper leaderboard →','查看论文榜单 →')}</a></div>`;
      return;
    }
    if (!state.draft) {
      app.innerHTML = `<div class="contribution-layout"><div><h3>${bi('Bring your results.','带上你的测评结果。')}</h3><p>${bi('Preview your summary, then submit on GitHub.','预览公开摘要，再以 GitHub 身份提交。')}</p>${picker(state)}</div>
        <div class="contribution-info"><p>${bi('<strong>Your GitHub identity.</strong><br>A review by the maintainers.<br>A place on the community board.','<strong>以 GitHub 账号署名。</strong><br>由维护者审核。<br>通过后进入社区榜单。')}</p></div></div>${instructions}`;
      return;
    }
    const draft = state.draft;
    app.innerHTML = `<div class="contribution-layout"><div><h3>${bi('Your submission','你的提交')}</h3><dl class="receipt-summary">
      <div><dt>${bi('Agent','系统')}</dt><dd>${escape(draft.metadata.agent)}</dd></div>
      <div><dt>${bi('Model','模型')}</dt><dd>${escape(draft.metadata.model)}</dd></div>
      <div><dt>${bi('Coverage','覆盖')}</dt><dd>${draft.coverage.tasks} ${bi('tasks','任务')} / ${draft.coverage.repetitions} ${bi('repetitions','次重复')}</dd></div>
      </dl>${picker(state)}</div><div class="contribution-info"><h3>${bi('Continue on GitHub','前往 GitHub')}</h3>
      <p>${bi('Only the summary is public. Original evidence stays private.','仅公开提交摘要，原始证据不随摘要上传。')}</p>
      <label class="public-consent"><input id="public-consent" type="checkbox">${bi('I have checked the public summary below.','我已核对下方将要公开的摘要。')}</label>
      <a class="github-link" id="github-draft" aria-disabled="true" tabindex="-1" target="_blank" rel="noopener noreferrer">${bi('Continue on GitHub','前往 GitHub')} <span aria-hidden="true">↗</span></a>
      </div></div><details><summary>${bi('Public summary','公开摘要')}</summary><pre>${escape(draft.body)}</pre></details>
      <details><summary>${bi('Review requirements','审核要求')}</summary><p>${bi('Ranking requires all 200 tasks, three Async repetitions and a maintainer review of the original evidence. A checked receipt is not an approved result.','上榜需要完整的 200 个任务、三次 Async 重复，以及维护者对原始证据的审核。回执检查通过不代表已获准上榜。')}</p></details>`;
  }
  root.addEventListener('click',event=>{
    const view = event.target.closest('[data-view]');
    if (view && root.contains(view)) controller.setView(view.dataset.view);
    const github = event.target.closest('#github-draft');
    if (github && github.getAttribute('aria-disabled')==='true') event.preventDefault();
  });
  root.addEventListener('change',event=>{
    if (event.target.id==='receipt-file') controller.upload(event.target.files?.[0]);
    if (event.target.id==='public-consent') {
      const link = root.querySelector('#github-draft');
      const enabled = event.target.checked && controller.state.draft?.url?.startsWith('https://github.com/pope8zdt/Async-RBench/issues/new?');
      link.setAttribute('aria-disabled',String(!enabled));
      link.tabIndex = enabled ? 0 : -1;
      if (enabled) link.href = controller.state.draft.url;
      else link.removeAttribute('href');
    }
  });
  render(controller.state);
}
