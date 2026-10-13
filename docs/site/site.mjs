import { rankResults, filterResults, filterTasks, parseTrace, publicEvent, scoreSummary } from './logic.mjs';

const root = document.documentElement;
const storageKey = 'async-rbench-paper-preferences';
const languageButton = document.getElementById('language');
const themeButton = document.getElementById('theme');
const language = () => root.lang === 'en' ? 'en' : 'zh';
const choose = (zh, en) => language() === 'zh' ? zh : en;
const savePreferences = () => {
  try { localStorage.setItem(storageKey, JSON.stringify({ language: language(), theme: root.dataset.theme })); } catch { /* Preferences are optional. */ }
};

function refreshLabels() {
  languageButton.textContent = choose('English', '中文');
  languageButton.setAttribute('aria-label', choose('Switch to English', '切换为中文'));
  const isDark = root.dataset.theme === 'dark';
  themeButton.textContent = isDark ? choose('浅色', 'Light') : choose('深色', 'Dark');
  themeButton.setAttribute('aria-label', isDark ? choose('切换为浅色主题', 'Switch to light theme') : choose('切换为深色主题', 'Switch to dark theme'));
  document.querySelectorAll('[data-zh][data-en]').forEach(element => { element.textContent = element.dataset[language()]; });
}

languageButton.addEventListener('click', () => {
  root.lang = language() === 'zh' ? 'en' : 'zh';
  savePreferences();
  refreshLabels();
  updateTasks();
});
themeButton.addEventListener('click', () => {
  root.dataset.theme = root.dataset.theme === 'dark' ? 'light' : 'dark';
  savePreferences();
  refreshLabels();
});
document.querySelectorAll('[data-enhance]').forEach(element => { element.hidden = false; });
refreshLabels();

const dataElement = document.getElementById('site-data');
const data = dataElement ? JSON.parse(dataElement.textContent) : null;
const modelSearch = document.getElementById('model-search');

function connectResults(bodyId, metricId, emptyId) {
  const resultBody = document.getElementById(bodyId);
  if (!resultBody || !data) return;
  const resultRows = new Map([...resultBody.children].map(row => [row.dataset.record, row]));
  const metric = document.getElementById(metricId);
  function updateResults() {
    const key = metric?.value || 'drs';
    const ranked = rankResults(data.paper.records, key);
    const shown = new Set(filterResults(ranked, modelSearch?.value || '').map(row => row.id));
    for (const record of ranked) {
      const row = resultRows.get(record.id);
      row.hidden = !shown.has(record.id);
      row.value = record.rank;
      row.dataset.place = record.rank;
      row.querySelector('.rank-number').textContent = String(record.rank).padStart(2, '0');
      row.querySelectorAll('[data-field]').forEach(field => {
        field.classList.toggle('is-ranked', field.dataset.field === key);
      });
      resultBody.append(row);
    }
    resultBody.dataset.metric = key;
    document.getElementById(emptyId).hidden = shown.size !== 0;
  }
  metric?.addEventListener('change', updateResults);
  modelSearch?.addEventListener('input', updateResults);
  updateResults();
}
connectResults('result-rows', 'metric', 'result-empty');
connectResults('success-rows', 'success-metric', 'success-empty');

const taskBody = document.getElementById('task-rows');
const taskSearch = document.getElementById('task-search');
const taskSource = document.getElementById('task-source');
const taskDifficulty = document.getElementById('task-difficulty');
function updateTasks() {
  if (!taskBody || !data) return;
  const filtered = filterTasks(data.tasks, { query: taskSearch.value, source: taskSource.value, difficulty: taskDifficulty.value });
  const shown = new Set(filtered.map(task => task.id));
  for (const row of taskBody.children) row.hidden = !shown.has(row.dataset.task);
  document.getElementById('task-count').textContent = shown.size === data.tasks.length
    ? choose('全部任务', 'All listed tasks')
    : `${shown.size} ${choose('个匹配任务', 'matching tasks')}`;
  document.getElementById('task-empty').hidden = shown.size !== 0;
}
taskSearch?.addEventListener('input', updateTasks);
taskSource?.addEventListener('change', updateTasks);
taskDifficulty?.addEventListener('change', updateTasks);
document.getElementById('task-reset')?.addEventListener('click', () => {
  taskSearch.value = '';
  taskSource.value = '';
  taskDifficulty.value = '';
  updateTasks();
});
updateTasks();

const replayRoot = document.querySelector('[data-replay]');
if (replayRoot) {
  const traceInput = document.getElementById('trace-file');
  const scoreInput = document.getElementById('score-file');
  const eventCard = document.getElementById('replay-event');
  const timeline = document.getElementById('replay-timeline');
  const position = document.getElementById('replay-position');
  const status = document.getElementById('replay-status');
  const play = document.getElementById('replay-play');
  let events = [];
  let cursor = 0;
  let timer = null;

  const stop = () => {
    if (timer) clearInterval(timer);
    timer = null;
    play.textContent = choose('播放', 'Play');
  };
  const setStatus = (zh, en) => { status.textContent = choose(zh, en); };
  const render = () => {
    eventCard.replaceChildren();
    timeline.querySelectorAll('button').forEach((button, index) => button.setAttribute('aria-current', index === cursor ? 'step' : 'false'));
    if (!events.length) {
      const message = document.createElement('p');
      message.textContent = choose('载入轨迹后，这里会显示当前事件。', 'The current event appears here after a trace is loaded.');
      eventCard.append(message);
      position.textContent = '0 / 0';
      return;
    }
    const event = publicEvent(events[cursor]);
    const title = document.createElement('h2');
    title.textContent = `${choose('事件', 'Event')} ${event.seq ?? cursor + 1}`;
    const details = document.createElement('dl');
    details.className = 'event-details';
    for (const [key, value] of Object.entries(event)) {
      const row = document.createElement('div');
      const term = document.createElement('dt');
      const description = document.createElement('dd');
      term.textContent = key;
      description.textContent = String(value);
      row.append(term, description);
      details.append(row);
    }
    eventCard.append(title, details);
    position.textContent = `${cursor + 1} / ${events.length}`;
  };
  const loadEvents = text => {
    events = parseTrace(text);
    cursor = 0;
    timeline.replaceChildren();
    events.forEach((event, index) => {
      const item = document.createElement('li');
      const button = document.createElement('button');
      const safe = publicEvent(event);
      button.type = 'button';
      button.textContent = `${safe.seq ?? index + 1} · ${safe.actor ?? safe.type ?? safe.status ?? choose('事件', 'event')}`;
      button.addEventListener('click', () => { stop(); cursor = index; render(); });
      item.append(button);
      timeline.append(item);
    });
    render();
    setStatus(`${events.length} 个事件已就绪。`, `${events.length} events ready.`);
  };
  const renderScore = value => {
    const score = scoreSummary(value);
    const fields = ['mode', 'drs', 'bts', 'status'];
    document.querySelectorAll('#replay-score dd').forEach((element, index) => {
      const value = score[fields[index]];
      element.textContent = value === undefined ? '—' : String(value);
    });
  };
  traceInput.addEventListener('change', async () => {
    try { loadEvents(await traceInput.files[0].text()); }
    catch (error) { stop(); setStatus(error.message, error.message); }
  });
  scoreInput.addEventListener('change', async () => {
    try { renderScore(JSON.parse(await scoreInput.files[0].text())); }
    catch { setStatus('score.json 无法解析。', 'score.json could not be parsed.'); }
  });
  document.getElementById('replay-demo').addEventListener('click', () => {
    loadEvents([
      { seq: 1, actor: 'controller', status: 'episode_started', elapsed_ms: 0 },
      { seq: 2, actor: 'main_agent', status: 'plan_created', elapsed_ms: 840 },
      { seq: 3, actor: 'child', child_id: 'worker-1', status: 'running', elapsed_ms: 1210 },
      { seq: 4, actor: 'gateway', result_id: 'result-1', status: 'delivered', elapsed_ms: 4880 },
      { seq: 5, actor: 'main_agent', status: 'replanned', reason: 'authoritative_result', elapsed_ms: 5360 },
      { seq: 6, actor: 'verifier', status: 'complete', elapsed_ms: 8110 },
    ].map(event => JSON.stringify(event)).join('\n'));
    renderScore({ mode: 'async', drs: 0.72, bts: 0.91, status: 'complete' });
  });
  document.getElementById('replay-reset').addEventListener('click', () => {
    stop(); events = []; cursor = 0; traceInput.value = ''; scoreInput.value = '';
    timeline.replaceChildren(); render(); renderScore({});
    setStatus('请选择文件或载入示例。', 'Choose files or load the demo.');
  });
  document.getElementById('replay-prev').addEventListener('click', () => { stop(); cursor = Math.max(0, cursor - 1); render(); });
  document.getElementById('replay-next').addEventListener('click', () => { stop(); cursor = Math.min(events.length - 1, cursor + 1); render(); });
  play.addEventListener('click', () => {
    if (timer) return stop();
    if (!events.length) return;
    play.textContent = choose('暂停', 'Pause');
    timer = setInterval(() => {
      if (cursor >= events.length - 1) return stop();
      cursor += 1;
      render();
    }, 800);
  });
  render();
}
