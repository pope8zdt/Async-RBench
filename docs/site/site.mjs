import { rankResults, filterResults, filterTasks } from './logic.mjs';

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
const resultBody = document.getElementById('result-rows');
const resultRows = resultBody ? new Map([...resultBody.children].map(row => [row.dataset.record, row])) : null;
const metric = document.getElementById('metric');
const modelSearch = document.getElementById('model-search');

function updateResults() {
  if (!resultBody || !data) return;
  const key = metric?.value || 'drs';
  const ranked = rankResults(data.paper.records, key);
  const shown = new Set(filterResults(ranked, modelSearch?.value || '').map(row => row.id));
  for (const record of ranked) {
    const row = resultRows.get(record.id);
    row.hidden = !shown.has(record.id);
    row.querySelector('.rank').textContent = record.rank === null ? '—' : String(record.rank).padStart(2, '0');
    resultBody.append(row);
  }
  const table = resultBody.closest('table');
  table.querySelectorAll('thead th').forEach(th => th.removeAttribute('aria-sort'));
  const column = { drs: 2, batched: 3, async: 4, delta: 5 }[key];
  table.querySelectorAll('thead th')[column].setAttribute('aria-sort', 'descending');
  document.getElementById('result-empty').hidden = shown.size !== 0;
}
metric?.addEventListener('change', updateResults);
modelSearch?.addEventListener('input', updateResults);
updateResults();

const taskBody = document.getElementById('task-rows');
const taskSearch = document.getElementById('task-search');
const taskSource = document.getElementById('task-source');
const taskDifficulty = document.getElementById('task-difficulty');
function updateTasks() {
  if (!taskBody || !data) return;
  const filtered = filterTasks(data.tasks, { query: taskSearch.value, source: taskSource.value, difficulty: taskDifficulty.value });
  const shown = new Set(filtered.map(task => task.id));
  for (const row of taskBody.children) row.hidden = !shown.has(row.dataset.task);
  document.getElementById('task-count').textContent = `${shown.size} / ${data.tasks.length} ${choose('任务', 'tasks')}`;
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
