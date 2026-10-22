import test from 'node:test';
import assert from 'node:assert/strict';

for (const guide of [true, false]) {
  test(`${guide ? 'submission guide without a footer control' : 'standard page with a footer control'} respects motion preferences`, async t => {
    const backdrop = {dataset: {}};
    const controls = [];
    const media = Object.assign(new EventTarget(), {matches: false});
    const document = Object.assign(new EventTarget(), {
      hidden: false,
      documentElement: {lang: 'en'},
      querySelector: selector => ({
        '.margin-motion': backdrop,
        '[data-submission-guide]': guide ? {} : null,
        footer: {append: control => controls.push(control)},
      })[selector] ?? null,
      createElement: () => Object.assign(new EventTarget(), {
        setAttribute(name, value) { this[name] = value; },
      }),
    });
    const stored = new Map();
    for (const [name, value] of Object.entries({document,
      matchMedia: () => media,
      sessionStorage: {getItem: key => stored.get(key), setItem: (key, value) => stored.set(key, value)},
      MutationObserver: class { observe() {} },
    })) {
      const prior = Object.getOwnPropertyDescriptor(globalThis, name);
      Object.defineProperty(globalThis, name, {value, configurable: true});
      t.after(() => prior ? Object.defineProperty(globalThis, name, prior) : delete globalThis[name]);
    }
    await import(`../published/margin-motion.mjs?guide=${guide}`);
    assert.equal(controls.length, guide ? 0 : 1);
    assert.equal(backdrop.dataset.moving, 'true');
    document.hidden = true;
    document.dispatchEvent(new Event('visibilitychange'));
    assert.equal(backdrop.dataset.moving, 'false');
    document.hidden = false;
    document.dispatchEvent(new Event('visibilitychange'));
    assert.equal(backdrop.dataset.moving, 'true');
    media.matches = true;
    media.dispatchEvent(new Event('change'));
    assert.equal(backdrop.dataset.moving, 'false');
    media.matches = false;
    media.dispatchEvent(new Event('change'));
    assert.equal(backdrop.dataset.moving, 'true');
    if (!guide) {
      controls[0].dispatchEvent(new Event('click'));
      assert.equal(backdrop.dataset.moving, 'false');
      assert.equal(stored.get('margin-motion-paused'), 'true');
      controls[0].dispatchEvent(new Event('click'));
      assert.equal(backdrop.dataset.moving, 'true');
    }
  });
}
