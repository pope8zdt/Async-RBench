const SCENE_MS = 16000;

export function sceneLink(id,singlePageRoot) {
  return singlePageRoot ? `${singlePageRoot}?case=${encodeURIComponent(id)}#trajectories` : `/trajectories/?case=${encodeURIComponent(id)}`;
}

export function playbackAllowed({paused, hidden, reduced}) {
  return !paused && !hidden && !reduced;
}

export function sceneState(elapsedMs, count) {
  if (!Number.isInteger(count) || count <= 0) return {scene: -1, phase: 0};
  const elapsed = Number.isFinite(elapsedMs) ? Math.max(0, elapsedMs) : 0;
  return {scene: Math.floor(elapsed / SCENE_MS) % count, phase: Math.floor((elapsed % SCENE_MS) / 4000)};
}

export class PlaybackClock {
  elapsed = 0;
  previous = null;
  wasRunning = false;
  tick(now, running) {
    if (running && this.wasRunning && this.previous !== null) this.elapsed += Math.max(0, now - this.previous);
    this.previous = now;
    this.wasRunning = running;
    return this.elapsed;
  }
}

function mount() {
  const scenes = [...document.querySelectorAll('[data-scene]')];
  if (!scenes.length) return;
  const root = document.documentElement;
  const languageButton = document.getElementById('entry-language');
  const motionButton = document.getElementById('entry-motion');
  const caption = document.querySelector('.archive-caption');
  const motionLabel = motionButton.querySelector('[data-motion-label]');
  const motionSymbol = motionButton.querySelector('.motion-symbol');
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const clock = new PlaybackClock();
  let userPaused = false;
  let timer;
  let lastScene = -1;
  let lastPhase = -1;
  const isEnglish = () => root.lang === 'en';
  const running = () => playbackAllowed({paused:userPaused, reduced:reduced.matches, hidden:document.hidden});

  function labels() {
    const paused = userPaused || reduced.matches;
    languageButton.textContent = isEnglish() ? '中文' : 'English';
    languageButton.setAttribute('aria-label', isEnglish() ? '切换至中文' : 'Switch to English');
    motionLabel.textContent = reduced.matches ? (isEnglish() ? 'Still background' : '静态背景') : paused ? (isEnglish() ? 'Play background' : '播放背景') : (isEnglish() ? 'Pause background' : '暂停背景');
    motionSymbol.textContent = paused ? '▷' : 'Ⅱ';
    motionButton.setAttribute('aria-pressed', String(paused));
    motionButton.disabled = reduced.matches;
    motionButton.title = reduced.matches ? (isEnglish() ? 'Your system reduces motion' : '已遵循系统减少动态效果设置') : '';
  }

  function update() {
    const state = sceneState(clock.tick(performance.now(), running()), scenes.length);
    if (state.scene === lastScene && state.phase === lastPhase) return;
    lastScene = state.scene;
    lastPhase = state.phase;
    scenes.forEach((scene, index) => {
      scene.classList.toggle('is-active', index === state.scene);
      if (index !== state.scene) return;
      scene.dataset.phase = state.phase;
      const events = [...scene.querySelectorAll('[data-event]')];
      const eventCount = scene.querySelector('.scene-plane').querySelectorAll('[data-event]').length;
      const active = Math.min(eventCount - 1, Math.floor(state.phase * eventCount / 4));
      events.forEach(event => event.classList.toggle('is-current', Number(event.dataset.event) === active));
    });
    document.querySelectorAll('[data-caption]').forEach(n => n.hidden = Number(n.dataset.caption) !== state.scene);
    caption.href = sceneLink(scenes[state.scene].dataset.scene,document.body.dataset.researchRoot);
  }

  function synchronize() {
    clearInterval(timer);
    clock.tick(performance.now(), false);
    root.classList.toggle('motion-running', running());
    labels();
    update();
    if (running()) timer = setInterval(update, 250);
  }

  languageButton.addEventListener('click', () => {
    root.lang = isEnglish() ? 'zh' : 'en';
    try {
      const key = 'async-rbench-paper-preferences';
      const saved = JSON.parse(localStorage.getItem(key) || '{}');
      localStorage.setItem(key, JSON.stringify({...saved, language: root.lang}));
    } catch { /* Language changes still work with unavailable storage. */ }
    labels();
  });
  motionButton.addEventListener('click', () => { userPaused = !userPaused; synchronize(); });
  reduced.addEventListener('change', synchronize);
  document.addEventListener('visibilitychange', synchronize);
  window.addEventListener('pagehide', () => { clearInterval(timer); clock.tick(performance.now(), false); });
  window.addEventListener('pageshow', synchronize);
  languageButton.hidden = false;
  motionButton.hidden = false;
  synchronize();
}

if (typeof document !== 'undefined') mount();
