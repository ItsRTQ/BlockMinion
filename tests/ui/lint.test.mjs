import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import path from 'node:path';

const STATIC = path.resolve(import.meta.dirname, '../../src/mod_orchestra/static');
const DIALOGS = ['confirmBox', 'promptBox', 'formBox', 'noticeBox'];

test('every dialog call in the page is awaited, because a Promise is always truthy', () => {
  // Regression: `if (!confirmBox(...))` never waited for the answer, so "Not now" still started a $12 designer run.
  const src = readFileSync(path.join(STATIC, 'app.js'), 'utf8');
  const bad = [];
  for (const name of DIALOGS) {
    for (const m of src.matchAll(new RegExp(`(.{0,24})\\b${name}\\(`, 'g'))) {
      if (!/(await|return)\s*$/.test(m[1])) bad.push(`${name}: …${m[1]}${name}(`);
    }
  }
  assert.deepEqual(bad, [], 'these calls are not awaited');
});

test('the page never calls a native popup', () => {
  for (const file of ['app.js', 'kit.js']) {
    const code = readFileSync(path.join(STATIC, file), 'utf8').split('\n').filter((l) => !l.trim().startsWith('//')).join('\n');
    assert.ok(!/(^|[^A-Za-z_.])(confirm|prompt|alert)\(/.test(code), `${file} calls a native popup`);
  }
});
