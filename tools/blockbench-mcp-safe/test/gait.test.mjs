import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {fileURLToPath} from 'node:url';
import {validateQuality} from '../src/quality.mjs';
import {gaitReport} from '../src/gait.mjs';

const rig = name => JSON.parse(readFileSync(fileURLToPath(new URL(`../../../src/mod_orchestra/resources/blockbench/rigs/${name}.bbmodel`, import.meta.url)), 'utf8'));
const gait = m => (validateQuality(m).warnings || []).filter(w => w.startsWith('GAIT_PHASE'));

// Move every keyframe of the lower-leg bones half a cycle later: the knee now flexes while the foot pushes back.
function knees_in_the_wrong_half(model) {
  const m = structuredClone(model);
  const shin = new Set(m.groups.filter(g => /(_shin|_lower)$/.test(g.name)).map(g => g.uuid));
  for (const a of m.animations.filter(a => /\.walk$/.test(a.name))) {
    for (const [uuid, animator] of Object.entries(a.animators)) {
      if (!shin.has(uuid) || !animator.keyframes) continue;
      const first = animator.keyframes.filter(k => k.time === 0);
      animator.keyframes = animator.keyframes.filter(k => k.time < a.length).map(k => ({...k, time: +((k.time + a.length / 2) % a.length).toFixed(4)}));
      for (const k of first) animator.keyframes.push({...structuredClone(k), uuid: k.uuid + 'e', time: a.length});
    }
  }
  return m;
}

for (const plan of ['quadruped', 'biped', 'insect']) {
  test(`${plan}: the base rig lifts every foot in the forward swing and the gate stays quiet`, () => {
    const m = rig(plan);
    const legs = gaitReport(m, `animation.${plan}.walk`);
    assert.ok(legs.length >= 2, 'has lower-leg bones');
    assert.deepEqual(legs.filter(l => !l.ok), []);
    assert.deepEqual(gait(m), []);
  });
}

// Where the knee does the lifting (the insect's femur lifts the foot itself, so moving only its tibia proves nothing).
for (const plan of ['quadruped', 'biped']) {
  test(`${plan}: knees flexing in the push-off half are reported`, () => {
    const warnings = gait(knees_in_the_wrong_half(rig(plan)));
    assert.ok(warnings.length >= 2, warnings.join('\n'));
    assert.match(warnings[0], /GAIT_PHASE: animation\.\w+\.walk lifts the foot of \w+ while it pushes backward/);
  });
}

test('models without lower-leg bones, or without a walk clip, are not judged', () => {
  assert.deepEqual(gait(rig('fish')), []);
  assert.deepEqual(gaitReport(rig('biped'), 'animation.biped.nope'), []);
});
