#!/usr/bin/env node
// Build one base rig from a recipe JSON with the vendored blockbench-mcp-safe code (no copies, no port):
//   node scripts/build_rig.mjs <recipe.json> <out_dir>
// Writes <plan>.bbmodel, <plan>.geo.json, <plan>.animation.json and prints the validate/quality report as JSON.
// UUIDs are rewritten deterministically (sha256 of plan:kind:name) so the committed files are diffable.
import {readFileSync, writeFileSync, mkdirSync} from 'node:fs';
import {createHash} from 'node:crypto';
import {join} from 'node:path';
import {editModel} from '../tools/blockbench-mcp-safe/src/model.mjs';
import {createGeckoModel, upsertAnimation, validateGecko, exportGeometry, exportAnimations} from '../tools/blockbench-mcp-safe/src/geckolib.mjs';
import {validateQuality} from '../tools/blockbench-mcp-safe/src/quality.mjs';

const [recipePath, outDir] = process.argv.slice(2);
if (!recipePath || !outDir) { console.error('usage: build_rig.mjs <recipe.json> <out_dir>'); process.exit(2); }
const r = JSON.parse(readFileSync(recipePath, 'utf8'));

const m = createGeckoModel({name: r.name, identifier: r.identifier, modid: r.modid, model_type: r.model_type ?? 'Entity',
  texture_width: r.texture_width, texture_height: r.texture_height});
if (Array.isArray(r.visible_box)) m.visible_box = r.visible_box;

const boneUuid = new Map();
for (const b of r.bones) {
  const op = {op: 'add_group', name: b.name, origin: b.origin, rotation: b.rotation};
  if (b.parent) { if (!boneUuid.has(b.parent)) throw Error(`bone ${b.name}: parent ${b.parent} must be declared first`); op.parent_group_uuid = boneUuid.get(b.parent); }
  const [out] = editModel(m, [op]);
  boneUuid.set(b.name, out.uuid);
}
for (const c of r.cubes) {
  if (!boneUuid.has(c.bone)) throw Error(`cube ${c.name}: unknown bone ${c.bone}`);
  const op = {op: 'add_cube', name: c.name, group_uuid: boneUuid.get(c.bone), from: c.from, to: c.to, uv_offset: c.uv_offset};
  if (c.inflate !== undefined) op.inflate = c.inflate;
  if (c.mirror !== undefined) op.mirror = c.mirror;
  if (c.rotation !== undefined) { op.rotation = c.rotation; op.origin = c.origin; }
  editModel(m, [op]);
}
for (const a of r.animations) upsertAnimation(m, {name: a.name, length: a.length, loop: a.loop, channels: a.channels});

// Deterministic UUIDs: every uuid the server generated is replaced by one derived from the plan and the object name.
const det = (kind, name) => {
  const h = createHash('sha256').update(`${r.plan}:${kind}:${name}`).digest('hex');
  return `${h.slice(0, 8)}-${h.slice(8, 12)}-4${h.slice(13, 16)}-8${h.slice(17, 20)}-${h.slice(20, 32)}`;
};
let text = JSON.stringify(m);
for (const g of m.groups) text = text.split(g.uuid).join(det('bone', g.name));
for (const e of m.elements) text = text.split(e.uuid).join(det('cube', e.name));
for (const a of m.animations ?? []) {
  text = text.split(a.uuid).join(det('anim', a.name));
  for (const [animatorUuid, animator] of Object.entries(a.animators ?? {}))
    for (const k of animator.keyframes ?? []) text = text.split(k.uuid).join(det('key', `${a.name}:${animator.name}:${k.channel}:${k.time}`));
}
const model = JSON.parse(text);

const report = {validate: validateGecko(model), quality: validateQuality(model)};
if (!report.validate.valid) { console.error(JSON.stringify(report, null, 2)); process.exit(1); }
mkdirSync(outDir, {recursive: true});
writeFileSync(join(outDir, `${r.plan}.bbmodel`), JSON.stringify(model, null, 2) + '\n');
writeFileSync(join(outDir, `${r.plan}.geo.json`), JSON.stringify(exportGeometry(model), null, 2) + '\n');
writeFileSync(join(outDir, `${r.plan}.animation.json`), JSON.stringify(exportAnimations(model), null, 2) + '\n');
console.log(JSON.stringify(report));
