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
  const reduced = matchMedia('(prefers-reduced-motion: reduce)');
  const clock = new PlaybackClock();
  let timer;
  let lastScene = -1;
  let lastPhase = -1;
  const isEnglish = () => root.lang === 'en';
  const running = () => playbackAllowed({paused:false, reduced:reduced.matches, hidden:document.hidden});

  function labels() {
    languageButton.textContent = isEnglish() ? '中文' : 'English';
    languageButton.setAttribute('aria-label', isEnglish() ? '切换至中文' : 'Switch to English');
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
  reduced.addEventListener('change', synchronize);
  document.addEventListener('visibilitychange', synchronize);
  window.addEventListener('pagehide', () => { clearInterval(timer); clock.tick(performance.now(), false); });
  window.addEventListener('pageshow', synchronize);
  languageButton.hidden = false;
  synchronize();
}

if (typeof document !== 'undefined') mount();
