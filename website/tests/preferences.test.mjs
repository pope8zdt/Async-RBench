import test from 'node:test';
import assert from 'node:assert/strict';
import {
  decodePreferences,
  savePreferences,
  preferenceKey,
} from '../lib/preferences.mjs';

test('new visitors use Chinese and their system color scheme', () => {
  assert.deepEqual(decodePreferences(null, true), {
    locale: 'zh',
    theme: 'dark',
  });
  assert.deepEqual(decodePreferences(null, false), {
    locale: 'zh',
    theme: 'light',
  });
});
test('saved choices survive a reload and override the system theme', () => {
  let stored;
  const storage = {
    setItem(key, value) {
      assert.equal(key, preferenceKey);
      stored = value;
    },
  };
  assert.equal(
    savePreferences(storage, { locale: 'en', theme: 'light' }),
    true,
  );
  assert.deepEqual(decodePreferences(stored, true), {
    locale: 'en',
    theme: 'light',
  });
});
test('corrupted or unsupported preferences fall back safely', () => {
  for (const value of [
    'broken',
    'null',
    '[]',
    '{"locale":"fr","theme":"pink"}',
  ]) {
    assert.deepEqual(decodePreferences(value, true), {
      locale: 'zh',
      theme: 'dark',
    });
  }
  assert.deepEqual(decodePreferences('{"locale":"en"}', false), {
    locale: 'en',
    theme: 'light',
  });
});
test('unavailable browser storage does not break preferences', () => {
  assert.equal(
    savePreferences(
      {
        setItem() {
          throw new Error('blocked');
        },
      },
      { locale: 'en', theme: 'dark' },
    ),
    false,
  );
});
