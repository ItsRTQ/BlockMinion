import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import path from 'node:path';
import os from 'node:os';
import {deflateSync} from 'node:zlib';
import {makeStore,readRaw,saveExisting} from '../src/storage.mjs';
import {runTool} from '../src/tools.mjs';
import {handle} from '../src/server.mjs';
import {parseModel} from '../src/model.mjs';
import {pngSize} from '../src/png.mjs';
import {validateGecko} from '../src/geckolib.mjs';

async function setup(t) {
  const root=await fs.mkdtemp(path.join(os.tmpdir(),'bbms-03-'));
  t.after(()=>fs.rm(root,{recursive:true,force:true}));
  const store=await makeStore(root);
  const created=await runTool(store,true,'bbmodel_geckolib_create',{file:'mob.bbmodel',name:'Mob',modid:'sample',identifier:'mob',texture_width:64,texture_height:64});
  const rig=await runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:created.revision,operations:[{op:'add_group',name:'body',origin:[0,12,0]}]});
  const bone=rig.changes[0].uuid;
  const cubes=await runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:rig.revision,operations:[{op:'add_cube',name:'part',group_uuid:bone,from:[-2,10,-2],to:[2,14,2],uv_offset:[0,0]}]});
  return {root,store,bone,revision:cubes.revision,cube:cubes.changes[0].uuid};
}
const keys=(channel='rotation',value=[0,0,0])=>[{bone:'body',channel,keyframes:[{time:0,value},{time:1,value}]}];
async function animation(store,rev,name='animation.mob.idle', channels=keys()) {
  return runTool(store,true,'bbmodel_geckolib_upsert_animation',{file:'mob.bbmodel',expected_revision:rev,name,length:1,loop:'loop',channels});
}

function crc32(bytes){let c=0xffffffff;for(const n of bytes){c^=n;for(let i=0;i<8;i++)c=c&1?(c>>>1)^0xedb88320:c>>>1;}return (c^0xffffffff)>>>0;}
function chunk(type,data){const name=Buffer.from(type,'ascii'),header=Buffer.alloc(4),checksum=Buffer.alloc(4);header.writeUInt32BE(data.length);checksum.writeUInt32BE(crc32(Buffer.concat([name,data])));return Buffer.concat([header,name,data,checksum]);}
function makePNG(w=64,h=64){
  const ihdr=Buffer.alloc(13);ihdr.writeUInt32BE(w,0);ihdr.writeUInt32BE(h,4);ihdr[8]=8;ihdr[9]=6;
  const rgba=Buffer.alloc((w*4+1)*h);
  for(let i=0;i<h;i++){rgba[i*(w*4+1)]=0;for(let x=0;x<w;x++)rgba[i*(w*4+1)+1+x*4+3]=255;}
  return Buffer.concat([Buffer.from('89504e470d0a1a0a','hex'),chunk('IHDR',ihdr),chunk('IDAT',deflateSync(rgba)),chunk('IEND',Buffer.alloc(0))]);
}

test('initialize announces safe workflow, X mirroring and updated version',async t=>{
  const {store}=await setup(t);
  const result=await handle({jsonrpc:'2.0',id:1,method:'initialize',params:{protocolVersion:'2025-06-18'}},store,false);
  assert.equal(result.result.serverInfo.version,'0.5.1');
  for(const instruction of ['bbmodel_edit','origin','uv_offset','require_idle_walk:true','revision','X'])assert.ok(result.result.instructions.includes(instruction),instruction);
});

test('Exports require explicit overwrite; overwrite is atomic, hashed, and rejects unsafe links',async t=>{
  const {root,store,revision}=await setup(t);
  for(const [tool,output_file] of [['bbmodel_geckolib_export_geometry','mob.geo.json'],['bbmodel_geckolib_export_animations','mob.animation.json']]){
    const params={file:'mob.bbmodel',output_file};
    const made=await runTool(store,true,tool,params);
    assert.equal(made.overwritten,false);assert.equal(made.path,output_file);assert.match(made.sha256,/^[a-f0-9]{64}$/);
    await assert.rejects(runTool(store,true,tool,params),{code:'EEXIST'});
    const old=await fs.readFile(path.join(root,output_file),'utf8');
    const updated=await runTool(store,true,tool,{...params,overwrite:true});
    assert.equal(updated.overwritten,true);assert.equal(updated.sha256,made.sha256);
    assert.equal(await fs.readFile(path.join(root,output_file),'utf8'),old);
    await assert.rejects(runTool(store,false,tool,{...params,overwrite:true}),/Write access disabled/);
    await assert.rejects(runTool(store,true,tool,{...params,overwrite:'true'}),/overwrite must be boolean/);
    await fs.unlink(path.join(root,output_file));
    await fs.symlink(path.join(root,'mob.bbmodel'),path.join(root,output_file));
    await assert.rejects(runTool(store,true,tool,{...params,overwrite:true}),/unsafe export target/);
  }
  assert.equal((await runTool(store,false,'bbmodel_info',{file:'mob.bbmodel'})).revision,revision);
});

test('Embedding verified PNG sets all cube face UUIDs and new cubes inherit texture',async t=>{
  const {root,store,revision,bone}=await setup(t);
  const png=makePNG();assert.deepEqual(pngSize(png),{width:64,height:64});
  await fs.writeFile(path.join(root,'skin.png'),png);
  const result=await runTool(store,true,'bbmodel_geckolib_set_texture',{file:'mob.bbmodel',expected_revision:revision,png_file:'skin.png'});
  assert.equal(result.change.width,64);
  const m=parseModel((await readRaw(store,'mob.bbmodel')).raw);
  assert.equal(m.textures[0].source,'data:image/png;base64,'+png.toString('base64'));
  assert.equal(m.textures[0].folder,'');assert.equal(m.textures[0].namespace,'');assert.equal(m.textures[0].id,'0');
  assert.ok(Object.values(m.elements[0].faces).every(face=>face.texture===m.textures[0].uuid));
  const newCube=await runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:result.revision,operations:[{op:'add_cube',name:'new',group_uuid:bone,from:[-1,0,-1],to:[1,2,1],uv_offset:[20,0]}]});
  const after=parseModel((await readRaw(store,'mob.bbmodel')).raw);
  assert.ok(Object.values(after.elements[1].faces).every(face=>face.texture===m.textures[0].uuid));
  assert.equal((await runTool(store,false,'bbmodel_geckolib_validate',{file:'mob.bbmodel'})).valid,true);
  await assert.rejects(runTool(store,true,'bbmodel_geckolib_set_texture',{file:'mob.bbmodel',expected_revision:revision,png_file:'skin.png'}),/Revision conflict/);
  assert.notEqual(newCube.revision,result.revision);
});

test('PNG safety: rejects mismatched resolution, tampered CRC, disguised file and symlink',async t=>{
  const {root,store,revision}=await setup(t);
  const call=()=>runTool(store,true,'bbmodel_geckolib_set_texture',{file:'mob.bbmodel',expected_revision:revision,png_file:'skin.png'});
  await fs.writeFile(path.join(root,'skin.png'),makePNG(16,16));await assert.rejects(call(),/uniform integer multiple/);
  const corrupted=makePNG();corrupted[29]^=1;await fs.writeFile(path.join(root,'skin.png'),corrupted);await assert.rejects(call(),/CRC mismatch/);
  await fs.writeFile(path.join(root,'skin.png'),Buffer.from('not-png'));await assert.rejects(call(),/not a valid PNG/);
  const invalidZlib=Buffer.concat([Buffer.from('89504e470d0a1a0a','hex'),chunk('IHDR',(()=>{const b=Buffer.alloc(13);b.writeUInt32BE(64);b.writeUInt32BE(64,4);b[8]=8;b[9]=6;return b;})()),chunk('IDAT',Buffer.from('not-zlib')),chunk('IEND',Buffer.alloc(0))]);
  await fs.writeFile(path.join(root,'skin.png'),invalidZlib);await assert.rejects(call(),/IDAT cannot be decoded/);
  await assert.rejects(runTool(store,true,'bbmodel_geckolib_set_texture',{file:'mob.bbmodel',expected_revision:revision,png_file:'../bad.png'}),/png_file must/);
  await fs.unlink(path.join(root,'skin.png'));await fs.symlink(path.join(root,'mob.bbmodel'),path.join(root,'skin.png'));
  await assert.rejects(call(),/unsafe PNG/);
  assert.equal((await runTool(store,false,'bbmodel_info',{file:'mob.bbmodel'})).revision,revision);
});

test('Replace-tracks=false merges tracks; remove_track and remove_animation preserve CAS',async t=>{
  const {store,revision}=await setup(t);
  const base=await animation(store,revision,'animation.mob.idle',keys('rotation'));
  const merge=await runTool(store,true,'bbmodel_geckolib_upsert_animation',{file:'mob.bbmodel',expected_revision:base.revision,name:'animation.mob.idle',length:1,loop:'loop',replace:true,replace_tracks:false,channels:keys('position',[1,0,0])});
  let m=parseModel((await readRaw(store,'mob.bbmodel')).raw);
  assert.deepEqual(new Set(Object.values(m.animations[0].animators)[0].keyframes.map(k=>k.channel)),new Set(['rotation','position']));
  const remove=await runTool(store,true,'bbmodel_geckolib_remove_track',{file:'mob.bbmodel',expected_revision:merge.revision,name:'animation.mob.idle',bone:'body',channel:'rotation'});
  assert.equal(remove.change.removed,true);
  m=parseModel((await readRaw(store,'mob.bbmodel')).raw);
  assert.deepEqual(Object.values(m.animations[0].animators)[0].keyframes.map(k=>k.channel),['position','position']);
  await assert.rejects(runTool(store,true,'bbmodel_geckolib_remove_track',{file:'mob.bbmodel',expected_revision:remove.revision,name:'animation.mob.idle',bone:'body',channel:'rotation'}),/Track not found/);
  const drop=await runTool(store,true,'bbmodel_geckolib_remove_animation',{file:'mob.bbmodel',expected_revision:remove.revision,name:'animation.mob.idle'});
  assert.equal(drop.change.removed,'animation.mob.idle');
  assert.equal((await runTool(store,false,'bbmodel_geckolib_validate',{file:'mob.bbmodel',require_idle_walk:true})).valid,false);
  await assert.rejects(runTool(store,true,'bbmodel_geckolib_remove_animation',{file:'mob.bbmodel',expected_revision:drop.revision,name:'animation.mob.idle'}),/Animation not found/);
});

test('Easing and catmullrom map to GeckoLib JSON without changing X coordinate convention',async t=>{
  const {store,revision}=await setup(t);
  const ch=[{bone:'body',channel:'rotation',keyframes:[{time:0,value:[10,20,30],interpolation:'catmullrom'},{time:1,value:[10,20,30],interpolation:'easeInOutSine'}]}];
  const created=await animation(store,revision,'animation.mob.idle',ch);
  const exported=(await runTool(store,false,'bbmodel_geckolib_export_animations',{file:'mob.bbmodel'})).output.animations['animation.mob.idle'].bones.body.rotation;
  assert.deepEqual(exported['0.0'],{vector:[-10,-20,30],lerp_mode:'catmullrom'});
  assert.deepEqual(exported['1.0'],{vector:[-10,-20,30],easing:'easeInOutSine'});
  await assert.rejects(runTool(store,true,'bbmodel_geckolib_upsert_animation',{file:'mob.bbmodel',expected_revision:created.revision,name:'animation.mob.bad',length:1,channels:[{bone:'body',channel:'rotation',keyframes:[{time:0,value:[0,0,0],interpolation:'arbitraryJavaScript'}]}]}),/Valid interpolation/);
});

test('Mirrored cube is exported with mirror:true; compact scene returns hierarchy',async t=>{
  const {store,revision,cube}=await setup(t);
  const updated=await runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:revision,operations:[{op:'update_cube',uuid:cube,mirror:true}]});
  const geometry=(await runTool(store,false,'bbmodel_geckolib_export_geometry',{file:'mob.bbmodel'})).output;
  assert.equal(geometry['minecraft:geometry'][0].bones[0].cubes[0].mirror,true);
  const scene=await runTool(store,false,'bbmodel_geckolib_read_scene',{file:'mob.bbmodel'});
  assert.equal(scene.bones[0].name,'body');assert.deepEqual(scene.bones[0].origin,[0,12,0]);
  assert.equal(scene.bones[0].cubes[0].uuid,cube);
  assert.equal(scene.bones[0].cubes[0].mirror,true);
  assert.equal(scene.revision,updated.revision);
});

test('Strict Gecko validation: oversized box UV error, empty bones warning, zero scale warning, late keyframe error',async t=>{
  const {store,revision,bone}=await setup(t);
  const oversized=await runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:revision,operations:[{op:'add_group',name:'empty_bone'}]});
  const warnings=await runTool(store,false,'bbmodel_geckolib_validate',{file:'mob.bbmodel'});
  assert.equal(warnings.valid,true);assert.ok(warnings.warnings.some(x=>x.includes('EMPTY_BONE: empty_bone')));
  await assert.rejects(runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:oversized.revision,operations:[{op:'add_cube',name:'too_big_uv',group_uuid:bone,from:[0,0,0],to:[4,4,4],uv_offset:[63,63]}]}),/UV_OUTSIDE_TEXTURE/);
  const scale=await animation(store,oversized.revision,'animation.mob.idle',keys('scale',[0,1,1]));
  const report=await runTool(store,false,'bbmodel_geckolib_validate',{file:'mob.bbmodel'});
  assert.equal(report.valid,true);assert.ok(report.warnings.some(x=>x.includes('KEYFRAME_SCALE_ZERO')));
  const broken=parseModel((await readRaw(store,'mob.bbmodel')).raw);broken.animations[0].length=0.5;
  const bad=validateGecko(broken);assert.equal(bad.valid,false);assert.ok(bad.errors.some(x=>x.includes('ANIMATION_LENGTH_BEFORE_LAST_KEYFRAME')));
  assert.equal(scale.revision,(await readRaw(store,'mob.bbmodel')).revision);
});

test('Write tools remain hidden/read-only when --allow-write disabled, including new tools',async t=>{
  const {store,revision}=await setup(t);
  const list=(await handle({jsonrpc:'2.0',id:1,method:'tools/list'},store,false)).result.tools.map(t=>t.name);
  for(const name of ['bbmodel_geckolib_set_texture','bbmodel_geckolib_remove_animation','bbmodel_geckolib_remove_track'])assert.ok(!list.includes(name));
  await assert.rejects(runTool(store,false,'bbmodel_geckolib_set_texture',{file:'mob.bbmodel',expected_revision:revision,png_file:'skin.png'}),/Write access disabled/);
  await assert.rejects(runTool(store,false,'bbmodel_geckolib_remove_animation',{file:'mob.bbmodel',expected_revision:revision,name:'animation.mob.idle'}),/Write access disabled/);
});

test('Iterative export writes changed geometry and animation SHA-256 after authorized revisions',async t=>{
  const {store,revision,cube}=await setup(t);
  const origG=await runTool(store,true,'bbmodel_geckolib_export_geometry',{file:'mob.bbmodel',output_file:'mob.geo.json'});
  const origA=await runTool(store,true,'bbmodel_geckolib_export_animations',{file:'mob.bbmodel',output_file:'mob.animation.json'});
  const edited=await runTool(store,true,'bbmodel_edit',{file:'mob.bbmodel',expected_revision:revision,operations:[{op:'update_cube',uuid:cube,mirror:true}]});
  const newG=await runTool(store,true,'bbmodel_geckolib_export_geometry',{file:'mob.bbmodel',output_file:'mob.geo.json',overwrite:true});
  assert.equal(newG.overwritten,true);assert.notEqual(newG.sha256,origG.sha256);
  const animated=await animation(store,edited.revision,'animation.mob.walk',keys('rotation'));
  const newA=await runTool(store,true,'bbmodel_geckolib_export_animations',{file:'mob.bbmodel',output_file:'mob.animation.json',overwrite:true});
  assert.equal(newA.overwritten,true);assert.notEqual(newA.sha256,origA.sha256);
  assert.equal(newA.source_revision,animated.revision);
});

test('Bundled textured example has embedded PNG, UUID-referenced faces and same geometry X convention',async()=>{
  const folder=path.resolve(import.meta.dirname??path.dirname(new URL(import.meta.url).pathname),'../examples');
  const raw=await fs.readFile(path.join(folder,'gecko_test_mob_textured.bbmodel'),'utf8');
  const model=parseModel(raw);
  const {valid,errors}=validateGecko(model);
  assert.equal(valid,true,errors.join('; '));
  assert.equal(model.textures.length,1);
  assert.match(model.textures[0].source,/^data:image\/png;base64,/);
  assert.ok(model.elements.every(c=>Object.values(c.faces).every(f=>f.texture===model.textures[0].uuid)));
  assert.deepEqual(pngSize(await fs.readFile(path.join(folder,'checker_64.png'))),model.resolution);
});

test('hi-res skin: a PNG at 2x the project resolution is embedded over the same UV layout and previewed at full detail',async t=>{
  const {root,store,revision}=await setup(t);
  const call=()=>runTool(store,true,'bbmodel_geckolib_set_texture',{file:'mob.bbmodel',expected_revision:revision,png_file:'skin.png'});
  await fs.writeFile(path.join(root,'skin.png'),makePNG(128,64));await assert.rejects(call(),/uniform integer multiple/);   // not uniform
  await fs.writeFile(path.join(root,'skin.png'),makePNG(128,128));
  const result=await call();
  assert.equal(result.change.width,128);assert.equal(result.change.scale,2);
  const m=parseModel((await readRaw(store,'mob.bbmodel')).raw);
  assert.deepEqual([m.textures[0].width,m.textures[0].height,m.textures[0].uv_width,m.textures[0].uv_height],[128,128,64,64]);   // UV space stays the project's
  assert.equal(m.resolution.width,64);
  assert.equal((await runTool(store,false,'bbmodel_geckolib_validate',{file:'mob.bbmodel'})).valid,true);
  const {renderModel}=await import('../src/render.mjs');
  const rendered=renderModel(m,{views:['front'],size:96});
  assert.equal(rendered.texture_applied,true);
});
