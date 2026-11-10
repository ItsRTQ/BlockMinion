// Render a .bbmodel to a PNG contact sheet with the vendored blockbench-mcp-safe renderer (no network).
// usage: node render_bbmodel.mjs <in.bbmodel> <out.png> [views=front,right,iso] [size=200]
import fs from 'node:fs';
import path from 'node:path';
import {pathToFileURL, fileURLToPath} from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const lib = path.join(here, '..', 'blockbench-mcp-safe', 'src');
const {renderModel} = await import(pathToFileURL(path.join(lib, 'render.mjs')).href);
const [input, output, viewsArg, sizeArg] = process.argv.slice(2);
if (!input || !output) { process.stderr.write('usage: render_bbmodel.mjs <in> <out.png> [views] [size]\n'); process.exit(1); }
let model;
try { model = JSON.parse(fs.readFileSync(input, 'utf8')); } catch (e) { process.stderr.write('not a .bbmodel\n'); process.exit(1); }
const views = (viewsArg || 'front,right,iso').split(',').map((v) => v.trim()).filter(Boolean);
const size = Math.max(64, Math.min(512, parseInt(sizeArg || '200', 10) || 200));
let out;
try { out = renderModel(model, {views, size, textures: false}); } catch (e) { process.stderr.write(String(e && e.message || e) + '\n'); process.exit(1); }
fs.mkdirSync(path.dirname(output), {recursive: true});
fs.writeFileSync(output, out.png);
process.stdout.write(JSON.stringify({views: out.views, width: out.width, height: out.height, triangles: out.triangles}));
