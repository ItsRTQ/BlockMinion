// Independent subset of GeckoLib / Blockbench 5.x project authoring.
// Purposefully supports numeric linear keyframes and box-UV cubes only.
import {randomUUID} from 'node:crypto';
import {createModel,inspect} from './model.mjs';

const NAME = /^[A-Za-z_][A-Za-z0-9_]{0,63}$/;
const NS = /^[a-z][a-z0-9_]{0,63}$/;
const ID = /^[a-z0-9_][a-z0-9_./-]{0,119}$/;
const CHANNELS = new Set(['rotation','position','scale']);
export const INTERPOLATIONS = ['linear','catmullrom','easeInSine','easeOutSine','easeInOutSine','easeInQuad','easeOutQuad','easeInOutQuad','easeInCubic','easeOutCubic','easeInOutCubic','easeInQuart','easeOutQuart','easeInOutQuart','easeInQuint','easeOutQuint','easeInOutQuint','easeInExpo','easeOutExpo','easeInOutExpo','easeInCirc','easeOutCirc','easeInOutCirc','easeInBack','easeOutBack','easeInOutBack','easeInBounce','easeOutBounce','easeInOutBounce','easeInElastic','easeOutElastic','easeInOutElastic'];
const INTERP_SET = new Set(INTERPOLATIONS);
const MAX_ANIMATIONS = 64;
const MAX_KEYFRAMES = 2000;
const obj = x => x !== null && typeof x === 'object' && !Array.isArray(x);
const fail = s => { throw new Error(s); };
const finite = (v,min,max) => typeof v === 'number' && Number.isFinite(v) && v >= min && v <= max;
const vec = (v,min=-2048,max=2048) => Array.isArray(v) && v.length===3 && v.every(x=>finite(x,min,max));
const zero = v => v.every(x=>x===0);
const clean = x => x===0 ? 0 : x;

function settings(m) {
  if (m.meta?.model_format!=='geckolib_model' || !String(m.meta.format_version||'').startsWith('5.')) fail('GeckoLib operation requires a Blockbench 5.x geckolib_model');
  if (!obj(m.resolution) || !Number.isInteger(m.resolution.width) || !Number.isInteger(m.resolution.height) || m.resolution.width<1 || m.resolution.width>2048 || m.resolution.height<1 || m.resolution.height>2048) fail('Invalid texture resolution');
  if (typeof m.mod_id!=='string' || !NS.test(m.mod_id)) fail('Invalid GeckoLib mod_id (lowercase namespace required)');
  if (typeof m.model_identifier!=='string' || !ID.test(m.model_identifier) || m.model_identifier.includes('..') || m.model_identifier.startsWith('/') || m.model_identifier.endsWith('/')) fail('Invalid model_identifier');
  if (!['Entity','Block','Item','Armor','Object'].includes(m.model_type)) fail('Invalid GeckoLib model_type');
}

export function createGeckoModel(opts) {
  const {name,identifier,modid,model_type='Entity',texture_width=64,texture_height=64}=opts;
  if (typeof name!=='string' || !name.length) fail('Name required');
  const m=createModel(name,texture_width,texture_height);
  m.meta.model_format='geckolib_model';
  m.model_identifier=identifier;
  m.mod_id=modid;
  m.model_type=model_type;
  m.visible_box=[2,3,1.5];
  m.animations=[];
  settings(m);
  return m;
}

function collect(m) {
  const groups=new Map((m.groups||[]).map(g=>[g.uuid,g]));
  const elements=new Map(m.elements.map(c=>[c.uuid,c]));
  const ordered=[], loose=[];
  function recurse(list,parent,depth) {
    if(depth>30) fail('Outliner depth exceeds limit');
    for (const entry of list) {
      if (typeof entry==='string') {
        const cube=elements.get(entry);
        if (!cube) fail('Unknown outliner cube');
        if (parent) parent.cubes.push(cube);
        else loose.push(cube);
      } else {
        const group=groups.get(entry.uuid);
        if(!group) fail('Unknown outliner bone');
        const bone={group,parent:parent?.group?.name,cubes:[]};
        ordered.push(bone);
        recurse(entry.children,bone,depth+1);
      }
    }
  }
  recurse(m.outliner,null,0);
  return {ordered,loose};
}

function validateAnimations(m, errors, warnings) {
  if (!Array.isArray(m.animations)) {errors.push('ANIMATIONS_MISSING: animations[] required');return;}
  if (m.animations.length>MAX_ANIMATIONS) errors.push('ANIMATION_LIMIT: Too many animations');
  const names=new Set();
  const groups=new Map((m.groups||[]).map(g=>[g.uuid,g]));
  let count=0;
  for (const a of m.animations) {
    if (!obj(a) || typeof a.name!=='string' || !/^animation\.[A-Za-z0-9_.-]{1,119}$/.test(a.name)) {errors.push('ANIMATION_NAME: Invalid animation name');continue;}
    if (names.has(a.name)) errors.push('ANIMATION_DUPLICATE: '+a.name);
    names.add(a.name);
    if (!finite(a.length,0.05,600)) errors.push('ANIMATION_LENGTH: '+a.name);
    if (!['once','loop','hold'].includes(a.loop)) errors.push('ANIMATION_LOOP: '+a.name);
    if (a.anim_time_update!==undefined || a.blend_weight!==undefined || a.start_delay!==undefined || a.loop_delay!==undefined) errors.push('ANIMATION_UNSUPPORTED_PROPERTIES: '+a.name);
    if (!obj(a.animators)) {errors.push('ANIMATORS_INVALID: '+a.name);continue;}
    for (const [id,animator] of Object.entries(a.animators)) {
      if (!groups.has(id)) {errors.push('ANIMATOR_UNKNOWN_BONE: '+id); continue;}
      if (!obj(animator) || !Array.isArray(animator.keyframes)) {errors.push('ANIMATOR_INVALID: '+id);continue;}
      if (animator.type && animator.type!=='bone') errors.push('ANIMATOR_UNSUPPORTED: '+id);
      if (animator.keyframes.length>MAX_KEYFRAMES) errors.push('KEYFRAME_LIMIT: '+id);
      const times=new Map();
      for (const key of animator.keyframes) {
        if (++count>MAX_KEYFRAMES) {errors.push('KEYFRAME_LIMIT: total limit exceeded');break;}
        if (!obj(key) || !CHANNELS.has(key.channel) || !finite(key.time,0,600) || !INTERP_SET.has(key.interpolation??'linear') || !Array.isArray(key.data_points) || key.data_points.length!==1 || !obj(key.data_points[0]) || !vec([key.data_points[0].x,key.data_points[0].y,key.data_points[0].z],-360,360)) {
          errors.push('KEYFRAME_INVALID: '+a.name+'/'+id);continue;
        }
        if (Object.keys(key).some(k=>!['uuid','channel','time','interpolation','data_points'].includes(k))) errors.push('KEYFRAME_UNSUPPORTED_PROPERTIES: '+a.name+'/'+id);
        if (key.time > a.length + 1e-6) errors.push('ANIMATION_LENGTH_BEFORE_LAST_KEYFRAME: '+a.name+'/'+id);
        if (key.channel==='scale') {
          const scale=[key.data_points[0].x,key.data_points[0].y,key.data_points[0].z];
          if (scale.some(v=>v<0)) errors.push('KEYFRAME_SCALE_NEGATIVE: scale must be >=0');
          else if(scale.some(v=>v===0)) warnings.push('KEYFRAME_SCALE_ZERO: '+a.name+'/'+groups.get(id).name+' may collapse the bone');
        }
        const signature=key.channel+':'+key.time.toFixed(6);
        if(times.has(signature)) errors.push('KEYFRAME_DUPLICATE: '+signature);
        times.set(signature,key.data_points[0]);
      }
      if (a.loop==='loop' && animator.keyframes.every(k=>obj(k)&&Array.isArray(k.data_points)&&obj(k.data_points[0])&&finite(k.time,0,a.length))) {
        for (const channel of CHANNELS) {
          const keys=animator.keyframes.filter(k=>k?.channel===channel).sort((a,b)=>a.time-b.time);
          if (!keys.length) continue;
          if (Math.abs(keys[0].time)>1e-6 || Math.abs(keys.at(-1).time-a.length)>1e-6) errors.push('LOOP_ENDPOINTS: '+a.name+'/'+groups.get(id).name+'/'+channel);
          else if (['x','y','z'].some(axis=>Math.abs(keys[0].data_points[0][axis]-keys.at(-1).data_points[0][axis])>1e-6)) errors.push('LOOP_SEAM: '+a.name+'/'+groups.get(id).name+'/'+channel);
        }
      }
    }
  }
}

export function validateGecko(m) {
  const basic=inspect(m);
  const errors=[...basic.errors], warnings=[...basic.warnings];
  // Validate source completeness instead of producing partial exports.
  if (!obj(m.resolution)) errors.push('RESOLUTION_INVALID');
  try {settings(m);} catch(e){errors.push('SETTINGS_INVALID: '+e.message);}
  if (!Array.isArray(m.groups)) errors.push('GROUPS_MISSING');
  else {
    const names=new Set();
    for(const g of m.groups) {
      if(!obj(g) || !NAME.test(g.name||'')) {errors.push('BONE_NAME: Invalid bone name');continue;}
      if(names.has(g.name)) errors.push('BONE_DUPLICATE: '+g.name);
      names.add(g.name);
      if(!vec(g.origin)||!vec(g.rotation,-360,360)) errors.push('BONE_TRANSFORM: '+g.name);
    }
  }
  try {
    const {loose,ordered}=collect(m);
    for (const bone of ordered) {
      const tree=(function find(nodes,id){for(const entry of nodes){if(obj(entry)){if(entry.uuid===id)return entry;const nested=find(entry.children||[],id);if(nested)return nested;}}return null;})(m.outliner,bone.group.uuid);
      if (tree?.children?.length===0 && !/^(held_item(_left)?|[a-z0-9_]+_locator)$/.test(bone.group.name)) warnings.push('EMPTY_BONE: '+bone.group.name+' has no cubes or child bones');   // held_item and *_locator are empty on purpose: the game attaches something to them
    }
    if(loose.length) errors.push('UNPARENTED_CUBES: '+loose.length+' cubes must belong to bones');
  } catch(e){errors.push('OUTLINER_INVALID: '+e.message);}
  if(Array.isArray(m.animation_controllers) && m.animation_controllers.length) errors.push('CONTROLLERS_UNSUPPORTED: animation controllers are not exported');
  for(const c of m.elements) {
    if (!obj(c) || (c.type!==undefined && c.type!=='cube') || !vec(c.from) || !vec(c.to) || !c.from.every((v,i)=>v<c.to[i])) {errors.push('CUBE_GEOMETRY: Unsupported or invalid cube (meshes require Generic .bbmodel; Bedrock poly_mesh deprecated)');continue;}
    if(c.box_uv===true) {
      if(!Array.isArray(c.uv_offset)||c.uv_offset.length!==2||!c.uv_offset.every(n=>Number.isInteger(n)&&n>=0&&n<=2048))errors.push('CUBE_UV: Invalid box UV offset');
    } else if(c.box_uv===false) {
      const sides=['north','south','east','west','up','down'];
      if(!obj(c.faces)||Object.keys(c.faces).some(s=>!sides.includes(s)))errors.push('FACE_UV: Unsupported face');
      else for(const [side,face] of Object.entries(c.faces)) {
        if(!obj(face)||!Array.isArray(face.uv)||face.uv.length!==4||!face.uv.every(n=>finite(n,0,2048))||
          ![undefined,0,90,180,270].includes(face.rotation))errors.push('FACE_UV_INVALID: '+(c.name||c.uuid)+'/'+side);
        else if(face.uv.some((v,i)=>v> (i%2===0?m.resolution.width:m.resolution.height)))errors.push('UV_OUTSIDE_TEXTURE: '+(c.name||c.uuid)+'/'+side);
      }
    } else errors.push('CUBE_UV: box_uv must be true or false');
    if (!vec(c.origin)||!vec(c.rotation,-360,360)||!finite(c.inflate??0,-16,16)) errors.push('CUBE_TRANSFORM: '+c.uuid);
    const dx=c.to[0]-c.from[0], dy=c.to[1]-c.from[1], dz=c.to[2]-c.from[2];
    if(c.box_uv===true&&c.uv_offset && obj(m.resolution) && (c.uv_offset[0]+2*(dx+dz)>m.resolution.width || c.uv_offset[1]+dy+dz>m.resolution.height)) errors.push('UV_OUTSIDE_TEXTURE: '+(c.name||c.uuid)+' box UV exceeds texture atlas dimensions');
    // Not silently discarding user-authored non-box UV or exports not implemented.
    if (c.export===false || c.visibility===false || c.autouv!==undefined || c.bedrock_binding!==undefined) errors.push('CUBE_UNSUPPORTED_FEATURE: '+c.uuid);
  }
  if (Array.isArray(m.textures) && m.textures.length) {
    if(m.textures.length!==1 || !obj(m.textures[0]) || typeof m.textures[0].uuid!=='string' || !/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(m.textures[0].source||'')) errors.push('TEXTURE_INVALID: only one embedded PNG texture is supported');
    else for(const c of m.elements) for(const face of Object.values(c.faces||{})) if(face?.texture!==null&&face?.texture!==m.textures[0].uuid) errors.push('TEXTURE_FACE_MISMATCH: '+c.uuid);
  }
  if(Array.isArray(m.groups)) for (const g of m.groups) if(g.export===false || g.visibility===false || g.bedrock_binding || g.mirror_uv) errors.push('BONE_UNSUPPORTED_FEATURE: '+g.name);
  if(Array.isArray(m.textures) && m.textures.length) warnings.push('TEXTURE_PNG_ASSET_REQUIRED: Exported GeckoLib geometry does not embed PNG; ship the PNG separately in mod assets');
  if(m.model_type==='Armor') warnings.push('ARMOR_TEMPLATE_UNVERIFIED: Armor requires special GeckoLib armor bones; not generated by this subset');
  validateAnimations(m,errors,warnings);
  return {valid:errors.length===0,errors:errors.slice(0,80),warnings:warnings.slice(0,50),counts:{bones:m.groups?.length||0,cubes:m.elements.length,animations:m.animations?.length||0}};
}

function requireValid(m) {
  const report=validateGecko(m);
  if(!report.valid) fail('GeckoLib validation failed: '+report.errors[0]);
  return report;
}

export function upsertAnimation(m, spec) {
  settings(m);
  const name=spec.name;
  if (typeof name!=='string' || !/^animation\.[A-Za-z0-9_.-]{1,119}$/.test(name)) fail('Animation name must start with animation.');
  const length=spec.length, loop=spec.loop??'once';
  if(!finite(length,0.05,600) || !['once','loop','hold'].includes(loop)) fail('Invalid animation length/loop');
  if(!Array.isArray(spec.channels) || spec.channels.length<1 || spec.channels.length>180) fail('channels must contain 1..180 entries');
  if(spec.replace_tracks !== undefined && typeof spec.replace_tracks !== 'boolean') fail('replace_tracks must be boolean');
  const boneByName=new Map();
  for(const g of m.groups||[]) {
    if(boneByName.has(g.name)) fail('Duplicate bone names');
    boneByName.set(g.name,g);
  }
  const animators=Object.create(null), used=new Set();
  let keys=0;
  for (const ch of spec.channels) {
    if(!obj(ch) || Object.keys(ch).some(k=>!['bone','channel','keyframes'].includes(k)) || typeof ch.bone!=='string' || !CHANNELS.has(ch.channel)) fail('Invalid channel');
    const bone=boneByName.get(ch.bone);
    if(!bone) fail('Animation references missing bone: '+ch.bone);
    if(used.has(ch.bone+':'+ch.channel)) fail('Duplicate channel for bone');
    used.add(ch.bone+':'+ch.channel);
    if(!Array.isArray(ch.keyframes) || ch.keyframes.length<1 || ch.keyframes.length>300) fail('Invalid keyframes count');
    if(!animators[bone.uuid]) animators[bone.uuid]={name:bone.name,type:'bone',keyframes:[]};
    let prev=-1;
    for (const k of ch.keyframes) {
      if(++keys>MAX_KEYFRAMES) fail('Too many keyframes');
      if(!obj(k) || Object.keys(k).some(z=>!['time','value','interpolation'].includes(z)) || !finite(k.time,0,length) || k.time<=prev || !vec(k.value,-360,360) || !INTERP_SET.has(k.interpolation??'linear')) fail('Invalid keyframe time/value/interpolation, or unsorted keyframes. Valid interpolation: '+INTERPOLATIONS.join(', '));
      if(ch.channel==='scale' && k.value.some(v=>v<0)) fail('Scale cannot be negative');
      prev=k.time;
      animators[bone.uuid].keyframes.push({uuid:randomUUID(),channel:ch.channel,time:k.time,interpolation:k.interpolation??'linear',data_points:[{x:k.value[0],y:k.value[1],z:k.value[2]}]});
    }
    if(loop==='loop') {
      const ks=ch.keyframes;
      if(Math.abs(ks[0].time)>1e-6 || Math.abs(ks.at(-1).time-length)>1e-6 || ks[0].value.some((v,i)=>Math.abs(v-ks.at(-1).value[i])>1e-6)) fail('Loop requires identical start/end pose at t=0 and t=length for each channel');
    }
  }
  const existing=(m.animations||[]).findIndex(a=>a.name===name);
  if(existing>=0 && !spec.replace) fail('Animation already exists (set replace: true to replace intentionally)');
  if(existing<0 && m.animations.length>=MAX_ANIMATIONS) fail('Animation limit reached');
  if(existing>=0 && spec.replace_tracks===false) {
    const old=m.animations[existing];
    for(const [uuid,oldAnimator] of Object.entries(old.animators)) {
      const modified=new Set((animators[uuid]?.keyframes||[]).map(k=>k.channel));
      const retained=oldAnimator.keyframes.filter(k=>!modified.has(k.channel));
      if(!animators[uuid]) animators[uuid]={name:oldAnimator.name,type:'bone',keyframes:[]};
      animators[uuid].keyframes.push(...retained);
    }
  }
  const anim={uuid:existing>=0?m.animations[existing].uuid:randomUUID(),name,loop,length,snapping:20,animators};
  if(existing>=0) m.animations[existing]=anim; else m.animations.push(anim);
  requireValid(m);
  return {animation:name,uuid:anim.uuid,channels:spec.channels.length,keyframes:keys,replace_tracks:spec.replace_tracks!==false};
}

export function removeAnimation(m,name) {
  settings(m);
  const index=m.animations.findIndex(a=>a.name===name);
  if(index<0) fail('Animation not found: '+name+'; valid names: '+m.animations.map(a=>a.name).join(', '));
  m.animations.splice(index,1);
  requireValid(m);
  return {removed:name};
}

export function removeAnimationTrack(m,name,bone,channel) {
  settings(m);
  if(!CHANNELS.has(channel)) fail('Invalid channel; valid: rotation, position, scale');
  const anim=m.animations.find(a=>a.name===name);
  if(!anim) fail('Animation not found: '+name);
  const group=m.groups.find(g=>g.name===bone);
  if(!group) fail('Bone not found: '+bone);
  const animator=anim.animators[group.uuid];
  if(!animator || !animator.keyframes.some(k=>k.channel===channel)) fail('Track not found: '+bone+'/'+channel);
  animator.keyframes=animator.keyframes.filter(k=>k.channel!==channel);
  if(!animator.keyframes.length) delete anim.animators[group.uuid];
  requireValid(m);
  return {animation:name,bone,channel,removed:true};
}

export function readGeckoScene(m) {
  settings(m);
  const groups=new Map(m.groups.map(g=>[g.uuid,g]));
  const cubes=new Map(m.elements.map(c=>[c.uuid,c]));
  const seen=new Set();
  const walk=(nodes,depth)=>{
    if(depth>30) fail('Too many nested bones');
    const result=[];
    for(const node of nodes) {
      if(typeof node==='string')fail('Unparented cube: '+node);
      const g=groups.get(node.uuid);if(!g)fail('Broken bone reference');if(seen.has(g.uuid))fail('Duplicate bone in tree');seen.add(g.uuid);
      const children=[];const inside=[];
      for(const entry of node.children||[]) {
        if(typeof entry==='string') {
          const c=cubes.get(entry);if(!c)fail('Broken cube reference');inside.push({uuid:c.uuid,name:c.name,from:c.from,to:c.to,uv_offset:c.uv_offset,mirror:c.mirror_uv===true});
        } else children.push(entry);
      }
      result.push({uuid:g.uuid,name:g.name,origin:g.origin,rotation:g.rotation,cubes:inside,children:walk(children,depth+1)});
    }
    return result;
  };
  return {model_identifier:m.model_identifier,mod_id:m.mod_id,resolution:m.resolution,bones:walk(m.outliner,0),animations:m.animations.map(a=>({name:a.name,length:a.length,loop:a.loop,tracks:Object.values(a.animators).reduce((sum,anim)=>sum+new Set(anim.keyframes.map(k=>k.channel)).size,0)}))};
}


export function exportGeometry(m) {
  requireValid(m);
  const {ordered}=collect(m);
  const bones=ordered.map(({group,parent,cubes})=>{
    const b={name:group.name};
    if(parent) b.parent=parent;
    b.pivot=[-group.origin[0],group.origin[1],group.origin[2]].map(clean);
    if (!zero(group.rotation)) b.rotation=[-group.rotation[0],-group.rotation[1],group.rotation[2]].map(clean);
    if (cubes.length) b.cubes=cubes.map(c=>{
      const cube={origin:[-c.to[0],c.from[1],c.from[2]].map(clean),size:c.from.map((v,i)=>clean(c.to[i]-v))};
      if(c.box_uv===true)cube.uv=[...c.uv_offset];
      else {
        cube.uv={};
        for(const [side,face] of Object.entries(c.faces)){
          if(face.texture===null)continue;
          const [u0,v0,u1,v1]=face.uv;
          let uv=[u0,v0],uvSize=[u1-u0,v1-v0];
          if(side==='up'||side==='down'){uv=[u1,v1];uvSize=[u0-u1,v0-v1];}
          const data={uv,uv_size:uvSize};
          if(face.rotation)data.uv_rotation=face.rotation;
          cube.uv[side]=data;
        }
      }
      if(c.inflate) cube.inflate=c.inflate;
      if(c.mirror_uv===true) cube.mirror=true;
      if(!zero(c.rotation)) {cube.pivot=[-c.origin[0],c.origin[1],c.origin[2]].map(clean);cube.rotation=[-c.rotation[0],-c.rotation[1],c.rotation[2]].map(clean);}
      return cube;
    });
    return b;
  });
  const bounds=Array.isArray(m.visible_box)&&m.visible_box.length===3&&m.visible_box.every(v=>finite(v,-10000,10000))?m.visible_box:[2,3,1.5];
  return {format_version:m.elements.some(c=>c.box_uv===false&&Object.values(c.faces||{}).some(f=>f.rotation))?'1.21.0':'1.12.0','minecraft:geometry':[{description:{identifier:'geometry.'+m.model_identifier,texture_width:m.resolution.width,texture_height:m.resolution.height,visible_bounds_width:bounds[0],visible_bounds_height:bounds[1],visible_bounds_offset:[0,bounds[2],0]},bones}]};
}

function outVector(channel,v) {
  if(channel==='rotation')return [-v.x,-v.y,v.z].map(clean);
  if(channel==='position')return [-v.x,v.y,v.z].map(clean);
  return [v.x,v.y,v.z].map(clean);
}
function timeText(t) {
  const value=String(Number(t.toFixed(6)));
  return value.includes('.')?value:value+'.0';
}
export function exportAnimations(m) {
  requireValid(m);
  const groups=new Map(m.groups.map(g=>[g.uuid,g]));
  const animations=Object.create(null);
  for(const a of m.animations) {
    const body={};
    if(a.loop==='loop') body.loop=true;
    if(a.loop==='hold') body.loop='hold_on_last_frame';
    body.animation_length=a.length;
    const bones=Object.create(null);
    for (const [uuid,animator] of Object.entries(a.animators)) {
      const name=groups.get(uuid).name;
      const channels=Object.create(null);
      for (const channel of CHANNELS) {
        const keys=animator.keyframes.filter(k=>k.channel===channel).sort((a,b)=>a.time-b.time);
        if(!keys.length)continue;
        const values=Object.create(null);
        for(const k of keys) {
          const item={vector:outVector(channel,k.data_points[0])};
          const mode=k.interpolation??'linear';
          if(mode==='catmullrom') item.lerp_mode='catmullrom';
          else if(mode!=='linear') item.easing=mode;
          values[timeText(k.time)]=item;
        }
        channels[channel]=values;
      }
      bones[name]=channels;
    }
    body.bones=bones;
    animations[a.name]=body;
  }
  return {format_version:'1.8.0',animations,geckolib_format_version:2};
}
