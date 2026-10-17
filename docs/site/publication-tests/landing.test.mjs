import test from 'node:test';
import assert from 'node:assert/strict';

test('cover without footer controls keeps rotating scenes, language switching and motion preferences', async t => {
  const node = (dataset = {}) => {
    const classes = new Set();
    return Object.assign(new EventTarget(), {
      dataset, hidden: true, textContent: '',
      setAttribute(name, value) { this[name] = value; },
      classList: {
        toggle(name, active) { active ? classes.add(name) : classes.delete(name); },
        contains(name) { return classes.has(name); },
      },
    });
  };
  const language = node();
  const root = Object.assign(node(), {lang: 'en'});
  const scenes = ['release', 'replay', 'early-stop'].map(id => {
    const events = [0, 1, 2, 3].map(event => node({event: String(event)}));
    return Object.assign(node({scene: id}), {
      querySelector: () => ({querySelectorAll: () => events}),
      querySelectorAll: () => events,
    });
  });
  const document = Object.assign(new EventTarget(), {
    documentElement: root, hidden: false,
    getElementById: id => id === 'entry-language' ? language : null,
    querySelector: () => null,
    querySelectorAll: selector => selector === '[data-scene]' ? scenes : [],
  });
  const media = Object.assign(new EventTarget(), {matches: false});
  const window = new EventTarget();
  const saved = new Map();
  let now = 0;
  for (const [name, value] of Object.entries({document, window,
    matchMedia: () => media,
    localStorage: {getItem: key => saved.get(key), setItem: (key, value) => saved.set(key, value)},
  })) {
    const prior = Object.getOwnPropertyDescriptor(globalThis, name);
    Object.defineProperty(globalThis, name, {value, configurable: true});
    t.after(() => prior ? Object.defineProperty(globalThis, name, prior) : delete globalThis[name]);
  }
  t.mock.method(performance, 'now', () => now);
  t.mock.timers.enable({apis: ['setInterval']});
  await import('../published/assets/landing.mjs?footerless-test');
  assert.equal(language.hidden, false);
  assert.equal(root.classList.contains('motion-running'), true);
  assert.equal(scenes[0].classList.contains('is-active'), true);
  now = 16500;
  t.mock.timers.tick(250);
  assert.equal(scenes[1].classList.contains('is-active'), true);
  language.dispatchEvent(new Event('click'));
  assert.equal(root.lang, 'zh');
  assert.equal(language.textContent, 'English');
  assert.equal(JSON.parse(saved.get('async-rbench-paper-preferences')).language, 'zh');
  document.hidden = true;
  document.dispatchEvent(new Event('visibilitychange'));
  assert.equal(root.classList.contains('motion-running'), false);
  now = 60000;
  t.mock.timers.tick(250);
  assert.equal(scenes[1].classList.contains('is-active'), true);
  document.hidden = false;
  document.dispatchEvent(new Event('visibilitychange'));
  assert.equal(root.classList.contains('motion-running'), true);
  media.matches = true;
  media.dispatchEvent(new Event('change'));
  assert.equal(root.classList.contains('motion-running'), false);
  media.matches = false;
  media.dispatchEvent(new Event('change'));
  assert.equal(root.classList.contains('motion-running'), true);
  window.dispatchEvent(new Event('pagehide'));
});
