import test from 'node:test';
import assert from 'node:assert/strict';
import {deflateSync, inflateSync} from 'node:zlib';
import {renderModel, cubeQuads, boxUvs} from '../src/render.mjs';

// Box-UV orientation as Blockbench defines it (cube.js): the four side faces show their texture rectangle upright and unmirrored seen from
// OUTSIDE; up and down use reversed rectangles (up is turned 180 degrees, down is mirrored horizontally).
const W = 32, H = 16;   // a cube 8x8x8 at uv_offset [0,0]: east [0,8,8,16] north [8,8,16,16] west [16,8,24,16] south [24,8,32,16] up [8,0,16,8] down [16,0,24,8]
const RECTS = {east: [0, 8, 8, 16], north: [8, 8, 16, 16], west: [16, 8, 24, 16], south: [24, 8, 32, 16], up: [8, 0, 16, 8], down: [16, 0, 24, 8]};
const RED = [255, 0, 0], GREEN = [0, 255, 0], BLUE = [0, 0, 255], WHITE = [255, 255, 255];

function crcTable() { const t = []; for (let n = 0; n < 256; n++) { let c = n; for (let k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1; t[n] = c >>> 0; } return t; }
const TABLE = crcTable();
function chunk(type, data) {
  const b = Buffer.alloc(12 + data.length); b.writeUInt32BE(data.length, 0); b.write(type, 4); data.copy(b, 8);
  let c = 0xffffffff; for (let i = 4; i < 8 + data.length; i++) c = TABLE[(c ^ b[i]) & 255] ^ (c >>> 8);
  b.writeUInt32BE((c ^ 0xffffffff) >>> 0, 8 + data.length); return b;
}
function markerSkin() {
  const px = Buffer.alloc(W * H * 4);
  const set = (x, y, c) => { const i = (y * W + x) * 4; px[i] = c[0]; px[i + 1] = c[1]; px[i + 2] = c[2]; px[i + 3] = 255; };
  for (const [u0, v0, u1, v1] of Object.values(RECTS)) {
    for (let y = v0; y < v1; y++) for (let x = u0; x < u1; x++) set(x, y, [110, 110, 110]);
    set(u0, v0, RED); set(u1 - 1, v0, GREEN); set(u0, v1 - 1, BLUE); set(u1 - 1, v1 - 1, WHITE);   // corners of the rectangle as an image: TL, TR, BL, BR
  }
  const ihdr = Buffer.alloc(13); ihdr.writeUInt32BE(W, 0); ihdr.writeUInt32BE(H, 4); ihdr[8] = 8; ihdr[9] = 6;
  const raw = Buffer.alloc((W * 4 + 1) * H);
  for (let y = 0; y < H; y++) { raw[y * (W * 4 + 1)] = 0; px.copy(raw, y * (W * 4 + 1) + 1, y * W * 4, (y + 1) * W * 4); }
  return Buffer.concat([Buffer.from('89504e470d0a1a0a', 'hex'), chunk('IHDR', ihdr), chunk('IDAT', deflateSync(raw)), chunk('IEND', Buffer.alloc(0))]);
}
function cube(extra = {}) {
  return {meta: {model_format: 'geckolib_model'}, resolution: {width: W, height: H}, groups: [{uuid: 'g', name: 'root', origin: [0, 0, 0], rotation: [0, 0, 0]}],
    outliner: [{uuid: 'g', children: ['c']}], elements: [{uuid: 'c', type: 'cube', name: 'c', from: [-4, 0, -4], to: [4, 8, 4], origin: [0, 0, 0], rotation: [0, 0, 0], box_uv: true, uv_offset: [0, 0], faces: {}, ...extra}],
    textures: [{uuid: 't', width: W, height: H, source: 'data:image/png;base64,' + markerSkin().toString('base64')}], animations: []};
}
function decode(png) {
  let pos = 8, idat = [], w, h;
  while (pos < png.length) { const len = png.readUInt32BE(pos), t = png.toString('ascii', pos + 4, pos + 8); if (t === 'IHDR') { w = png.readUInt32BE(pos + 8); h = png.readUInt32BE(pos + 12); } if (t === 'IDAT') idat.push(png.subarray(pos + 8, pos + 8 + len)); pos += 12 + len; }
  const data = inflateSync(Buffer.concat(idat)), stride = w * 4 + 1;
  return {w, h, at: (x, y) => [0, 1, 2].map(k => data[y * stride + 1 + x * 4 + k])};
}
const kind = c => { const [r, g, b] = c; const hi = Math.max(r, g, b), lo = Math.min(r, g, b);
  if (hi - lo < 25) return hi > 100 ? 'white' : 'gray'; return r === hi ? 'red' : g === hi ? 'green' : 'blue'; };
// The colours at the four corners (inset 6%) of the cube's silhouette in a view: [TL, TR, BL, BR]
function corners(view) {
  const {png} = renderModel(cube(), {views: [view], size: 192});
  const img = decode(png);
  let x0 = 1e9, x1 = -1, y0 = 1e9, y1 = -1;
  for (let y = 0; y < img.h; y++) for (let x = 0; x < img.w; x++) { const c = img.at(x, y); if (!(Math.abs(c[0] - 25) < 3 && Math.abs(c[1] - 32) < 3 && Math.abs(c[2] - 45) < 3)) { x0 = Math.min(x0, x); x1 = Math.max(x1, x); y0 = Math.min(y0, y); y1 = Math.max(y1, y); } }
  const ix = (x1 - x0) * 0.06, iy = (y1 - y0) * 0.06;
  return [[x0 + ix, y0 + iy], [x1 - ix, y0 + iy], [x0 + ix, y1 - iy], [x1 - ix, y1 - iy]].map(([x, y]) => kind(img.at(Math.round(x), Math.round(y))));
}

for (const view of ['front', 'back', 'left', 'right']) {
  test(`${view} view: a side face shows its texture rectangle upright and unmirrored`, () => {
    assert.deepEqual(corners(view), ['red', 'green', 'blue', 'white']);   // top-left, top-right, bottom-left, bottom-right of the rectangle as an image
  });
}

test('top view: the up face is the reversed rectangle, so the image appears turned 180 degrees with its bottom edge toward the north', () => {
  assert.deepEqual(corners('top'), ['white', 'blue', 'green', 'red']);
});

test('quads are top-left, top-right, bottom-right, bottom-left as seen from outside', () => {
  const q = cubeQuads([0, 0, 0], [8, 6, 4]);
  assert.deepEqual(q.north[0], [8, 6, 0]); assert.deepEqual(q.north[1], [0, 6, 0]); assert.deepEqual(q.north[3], [8, 0, 0]);   // seen from the north, +x is on the left
  assert.deepEqual(q.south[0], [0, 6, 4]); assert.deepEqual(q.south[1], [8, 6, 4]);
  assert.deepEqual(q.east[0], [8, 6, 4]); assert.deepEqual(q.east[1], [8, 6, 0]);
  assert.deepEqual(q.west[0], [0, 6, 0]); assert.deepEqual(q.west[1], [0, 6, 4]);
  assert.deepEqual(q.up[0], [0, 6, 0]); assert.deepEqual(q.up[2], [8, 6, 4]);
});

test('box-UV rectangles follow Blockbench: sizes are floored, up and down are reversed, down is w wide', () => {
  const c = {from: [0, 0, 0], to: [8.9, 6, 4], uv_offset: [10, 20]};   // 8 x 6 x 4 after flooring
  assert.deepEqual(boxUvs(c, 'north'), [14, 24, 22, 30]);
  assert.deepEqual(boxUvs(c, 'up'), [22, 24, 14, 20]);
  assert.deepEqual(boxUvs(c, 'down'), [30, 20, 22, 24]);   // 8 wide (w), not 4 (d)
  assert.deepEqual(boxUvs(c, 'east'), [10, 24, 14, 30]);
  assert.deepEqual(boxUvs(c, 'south'), [26, 24, 34, 30]);
});
