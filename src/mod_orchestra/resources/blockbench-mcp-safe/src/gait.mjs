// Gait check: does a walk or run clip lift each foot while it travels FORWARD (the swing) rather than while it pushes back?
// Forward kinematics with the same Euler order as the previewer (three.js ZYX); the creature faces -Z.
// A lower-leg bone is one whose name ends in _shin or _lower (the names the rig library and the skill use).
import {samplePose} from './pose.mjs';

const rad = d => d * Math.PI / 180;
function rot(v, deg) {
  const [rx, ry, rz] = deg.map(rad), [sx, cx] = [Math.sin(rx), Math.cos(rx)], [sy, cy] = [Math.sin(ry), Math.cos(ry)], [sz, cz] = [Math.sin(rz), Math.cos(rz)];
  const x = [v[0], v[1] * cx - v[2] * sx, v[1] * sx + v[2] * cx], y = [x[0] * cy + x[2] * sy, x[1], -x[0] * sy + x[2] * cy];
  return [y[0] * cz - y[1] * sz, y[0] * sz + y[1] * cz, y[2]];
}

export const LOWER_LEG = /(_shin|_lower)$/;

export function gaitReport(model, clip, samples = 16) {
  const anim = (model.animations || []).find(a => a.name === clip);
  if (!anim || !(anim.length > 0)) return [];
  const parentOf = {}, cubesOf = {};
  const walk = (nodes, parent) => { for (const n of nodes || []) if (typeof n !== 'string') { parentOf[n.uuid] = parent; cubesOf[n.uuid] = (n.children || []).filter(c => typeof c === 'string'); walk(n.children, n.uuid); } };
  walk(model.outliner, null);
  const elem = Object.fromEntries((model.elements || []).map(e => [e.uuid, e]));
  const poses = Array.from({length: samples}, (_, i) => {
    const pose = samplePose(model, {animation: clip, time: anim.length * i / samples, wrap: false});
    return Object.fromEntries(pose.bones.map(b => [b.uuid, b]));
  });
  const out = [];
  for (const leg of (model.groups || []).filter(g => LOWER_LEG.test(g.name))) {
    const cubes = (cubesOf[leg.uuid] || []).map(u => elem[u]).filter(Boolean);
    if (!cubes.length) continue;
    const low = cubes.reduce((a, b) => (a.from[1] < b.from[1] ? a : b));
    const foot = [(low.from[0] + low.to[0]) / 2, low.from[1], (low.from[2] + low.to[2]) / 2];
    const track = poses.map(local => {
      let p = foot, u = leg.uuid;
      while (u) {
        const b = local[u], total = [0, 1, 2].map(k => (b.rest_rotation?.[k] || 0) + b.rotation[k]);
        p = rot(p.map((v, k) => v - b.pivot[k]), total).map((v, k) => v + b.pivot[k] + b.position[k]);
        u = parentOf[u];
      }
      return p;
    });
    const N = track.length, minY = Math.min(...track.map(p => p[1])), maxY = Math.max(...track.map(p => p[1])), range = maxY - minY;
    // The highest point(s) of the foot: every sample within 3% of the range of the maximum (a limb that swings like a pendulum peaks at the end of its arc,
    // where two neighbouring samples are nearly equally high and one travels forward while the other travels back). Where does that set of samples travel?
    const step = i => track[(i + 1) % N][2] - track[i][2];                      // the creature faces -Z: negative = forward
    const peaks = track.map((p, i) => i).filter(i => track[i][1] >= maxY - 0.03 * range);
    const travel = peaks.reduce((sum, i) => sum + (track[(i + 1) % N][2] - track[(i - 1 + N) % N][2]), 0);
    const lift = i => (track[i][1] + track[(i + 1) % N][1]) / 2 - minY, fwd = [], back = [];
    for (let i = 0; i < N; i++) (step(i) < 0 ? fwd : back).push(lift(i));
    const mean = a => a.length ? a.reduce((x, y) => x + y, 0) / a.length : 0;
    const clearlyHigherInSwing = mean(fwd) >= 1.15 * mean(back);                // the second way to pass: on average well above the ground while travelling forward than while pushing back
    const verdict = travel < -1e-6 ? 'forward' : clearlyHigherInSwing ? 'forward' : travel > 1e-6 ? 'backward' : 'turning';
    out.push({bone: leg.name, peak_while: verdict, range: +range.toFixed(2), ok: range < 0.15 || travel < -1e-6 || clearlyHigherInSwing});   // a foot that barely lifts is not a gait problem; otherwise its highest point must be in the swing
  }
  return out;
}

export function gaitWarnings(model) {
  const warnings = [];
  for (const a of model.animations || []) {
    if (!/(^|\.)(walk|run)$/.test(a.name)) continue;
    for (const leg of gaitReport(model, a.name)) {
      if (!leg.ok) warnings.push(`GAIT_PHASE: ${a.name} lifts the foot of ${leg.bone} while it pushes backward (peak ${leg.peak_while}); flex the knee during the forward swing so the foot leaves the ground only when it moves forward`);
    }
  }
  return warnings;
}
