// Export a user's .bbmodel to GeckoLib files with the vendored blockbench-mcp-safe exporter (no network, no npm).
// usage: node export_bbmodel.mjs <in.bbmodel> <out_dir> <mob_id> <mod_id>
// writes <out_dir>/out.bbmodel (normalized), <mob>.geo.json, <mob>.animation.json and <mob>.png when a texture is embedded;
// prints {bones, clips, embedded_texture, normalized} as JSON. Any failure exits 1 with the reason on stderr.
import fs from 'node:fs';
import path from 'node:path';
import {fileURLToPath, pathToFileURL} from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const lib = path.join(here, '..', 'blockbench-mcp-safe', 'src');
const {exportGeometry, exportAnimations} = await import(pathToFileURL(path.join(lib, 'geckolib.mjs')).href);

const [input, outDir, mob, modId] = process.argv.slice(2);
const die = (msg) => { process.stderr.write(String(msg) + '\n'); process.exit(1); };
if (!input || !outDir || !/^[a-z][a-z0-9_]{1,49}$/.test(mob || '') || !/^[a-z][a-z0-9_]{1,63}$/.test(modId || '')) die('usage: export_bbmodel.mjs <in> <out_dir> <mob> <mod_id>');

let m;
try { m = JSON.parse(fs.readFileSync(input, 'utf8')); } catch (e) { die('not a .bbmodel (invalid JSON)'); }
if (!m || typeof m !== 'object' || !Array.isArray(m.elements) || !Array.isArray(m.outliner)) die('not a supported .bbmodel structure (no elements/outliner)');
const notes = [];

// Blockbench 4.x keeps bones inline in the outliner; the exporter wants the 5.x `groups` list plus uuid references.
if (!Array.isArray(m.groups)) {
  m.groups = [];
  const lift = (nodes) => (nodes || []).map((n) => {
    if (typeof n === 'string') return n;
    m.groups.push({uuid: n.uuid, name: n.name, origin: n.origin || [0, 0, 0], rotation: n.rotation || [0, 0, 0]});
    return {uuid: n.uuid, isOpen: true, children: lift(n.children)};
  });
  m.outliner = lift(m.outliner);
  notes.push('bones lifted from a Blockbench 4.x outliner');
}
for (const g of m.groups) { g.origin = g.origin || [0, 0, 0]; g.rotation = g.rotation || [0, 0, 0]; }
m.meta = {...(m.meta || {}), model_format: 'geckolib_model', box_uv: true};
m.model_identifier = mob; m.mod_id = modId;
m.animations = m.animations || [];
const num = (v, where) => {
  if (typeof v === 'number') return v;
  const t = String(v).trim();
  if (t === '') return 0;
  const n = Number(t);
  if (!Number.isFinite(n)) die(`a keyframe uses an expression (${where}: "${t}"); only plain numbers are supported`);
  return n;
};
const names = new Set();
for (const a of m.animations) {   // GeckoLib looks clips up as animation.<mob>.<clip>: an outside model may say `idle` or `animation.model.idle`
  const short = String(a.name || '').split('.').pop().trim().toLowerCase().replace(/[^a-z0-9_]+/g, '_');
  if (!short) die('a clip has no name');
  const name = `animation.${mob}.${short}`;
  if (names.has(name)) die(`two clips end in "${short}"`);
  if (name !== a.name) notes.push(`clip ${a.name} -> ${name}`);
  names.add(name); a.name = name;
}
for (const a of m.animations) {
  a.loop = a.loop || 'once'; a.length = num(a.length ?? 0, a.name + ' length');
  for (const [uuid, an] of Object.entries(a.animators || {})) {
    if (!m.groups.some((g) => g.uuid === uuid)) { delete a.animators[uuid]; continue; }   // effects/timeline animators carry no bone
    for (const k of an.keyframes || []) {
      k.time = num(k.time, a.name + ' time');
      k.data_points = (k.data_points || []).map((p) => ({x: num(p.x, a.name), y: num(p.y, a.name), z: num(p.z, a.name)}));
    }
  }
}

let geo, anim;
try { geo = exportGeometry(m); anim = exportAnimations(m); } catch (e) { die(e && e.message ? e.message : e); }
fs.mkdirSync(outDir, {recursive: true});
let embedded = false;
const tex = (m.textures || [])[0];
if (tex && typeof tex.source === 'string' && tex.source.startsWith('data:image/png;base64,')) {
  fs.writeFileSync(path.join(outDir, mob + '.png'), Buffer.from(tex.source.slice('data:image/png;base64,'.length), 'base64'));
  embedded = true;
}
fs.writeFileSync(path.join(outDir, 'out.bbmodel'), JSON.stringify(m));
fs.writeFileSync(path.join(outDir, mob + '.geo.json'), JSON.stringify(geo, null, 2) + '\n');
fs.writeFileSync(path.join(outDir, mob + '.animation.json'), JSON.stringify(anim, null, 2) + '\n');
process.stdout.write(JSON.stringify({bones: geo['minecraft:geometry'][0].bones.length, clips: Object.keys(anim.animations || {}), embedded_texture: embedded, normalized: notes}));
