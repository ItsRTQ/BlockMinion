import {filename,readRaw,listFiles,saveNew,saveExisting,saveExport,readWorkspacePng} from './storage.mjs';
import {createModel,parseModel,editModel,inspect,overview} from './model.mjs';
import {createGeckoModel,validateGecko,upsertAnimation,removeAnimation,removeAnimationTrack,readGeckoScene,INTERPOLATIONS,exportGeometry,exportAnimations} from './geckolib.mjs';
import {readLive} from './live.mjs';
import {samplePose} from './pose.mjs';
import {validateQuality} from './quality.mjs';
import {renderModel} from './render.mjs';
import {savePreview} from './storage.mjs';
import {embedTexture} from './png.mjs';

const fileSchema = {type:'string',pattern:'^[A-Za-z0-9][A-Za-z0-9._-]{0,119}\\.bbmodel$'};
const vectorSchema = {type:'array',items:{type:'number'},minItems:3,maxItems:3};
const shape = (properties,required=[]) => ({type:'object',properties,required,additionalProperties:false});
const spec = (name,description,inputSchema,writes=false,live=false) => ({name,description,inputSchema,writes,live});

const OPERATIONS = ['add_cube','update_cube','remove_cube','add_group','rename_group','set_bone_transform','remove_empty_group','add_mesh','remove_mesh'];
const KF = shape({time:{type:'number'},value:vectorSchema,interpolation:{type:'string',enum:INTERPOLATIONS}},['time','value']);
const uvFaceShape=shape({uv:{type:'array',items:{type:'number'},minItems:4,maxItems:4},rotation:{type:'integer',enum:[0,90,180,270]},enabled:{type:'boolean'}},['uv']);
const uvFacesSchema={type:'object',properties:Object.fromEntries(['north','south','east','west','up','down'].map(x=>[x,uvFaceShape])),additionalProperties:false};
const channelSchema = shape({bone:{type:'string'},channel:{type:'string',enum:['rotation','position','scale']},keyframes:{type:'array',minItems:1,maxItems:300,items:KF}},['bone','channel','keyframes']);
export const TOOLS = [
  spec('app_status','Optional read-only Blockbench desktop bridge: recent status snapshot, requires --enable-live and manual plugin connection.',shape({}),false,true),
  spec('app_read_scene','Optional read-only Blockbench desktop bridge: current cubes/bones snapshot, no mutations.',shape({}),false,true),
  spec('app_capture_screenshot','Optional best-effort read-only Blockbench viewport PNG snapshot. May be unavailable depending on GPU/driver.',shape({}),false,true),
  spec('bbmodel_sample_pose','Sample numeric animation transforms at time in seconds; includes interpolation and loop wrap; local bone transforms only.',shape({file:fileSchema,animation:{type:'string'},time:{type:'number'},wrap:{type:'boolean'}},['file','animation','time'])),
  spec('bbmodel_quality_gates','Quality assessment: rig depth, bounds, bone/cube limits, extreme proportions and thin geometry.',shape({file:fileSchema,max_span:{type:'number'},max_axis_ratio:{type:'number'},max_cubes:{type:'number'},max_bones:{type:'number'},min_thickness:{type:'number'},max_bone_depth:{type:'number'},fail_on_warnings:{type:'boolean'}},['file'])),
  spec('bbmodel_render','Textured CPU PNG/contact sheet, views front/back/left/right/top/iso. Applies embedded PNG UVs and bone animation at time (seconds); animation requires a GeckoLib clip. No GPU or exact Blockbench parity. Writes optional PNG only with --allow-write.',shape({file:fileSchema,views:{type:'array',minItems:1,maxItems:6,items:{type:'string',enum:['front','back','left','right','top','iso']}},size:{type:'integer',minimum:64,maximum:320},textures:{type:'boolean'},animation:{type:'string'},time:{type:'number',minimum:0},wrap:{type:'boolean'},output_file:{type:'string'},overwrite:{type:'boolean'}},['file'])),
  spec('bbmodel_list_files' ,'List .bbmodel files immediately inside the configured workspace (no recursive traversal).',shape({})),
  spec('bbmodel_info','Read a model summary and SHA-256 revision. Does not expose texture bytes.',shape({file:fileSchema},['file'])),
  spec('bbmodel_read_scene','Read geometry, groups and hierarchy for models with <=250 elements.',shape({file:fileSchema},['file'])),
  spec('bbmodel_validate','Validate basic references and geometry, reporting warnings; not a full Blockbench format validation.',shape({file:fileSchema},['file'])),
  spec('bbmodel_create','Create a new Blockbench 5.x Generic .bbmodel, refusing overwrite. Requires --allow-write.',shape({file:fileSchema,name:{type:'string',maxLength:80},texture_width:{type:'integer',minimum:1,maximum:2048},texture_height:{type:'integer',minimum:1,maximum:2048}},['file']),true),
  spec('bbmodel_edit','Atomically edit a Generic or GeckoLib 5.x model. Requires an exact expected_revision from bbmodel_info. Operations: add_cube (name,from,to, optional group_uuid/origin/rotation); update_cube (uuid + fields); remove_cube (uuid); add_group (name, optional parent_group_uuid/origin); rename_group (uuid,name); remove_empty_group (uuid). Untextured geometry only. Requires --allow-write.',
    shape({file:fileSchema,expected_revision:{type:'string',pattern:'^[0-9a-f]{64}$'},operations:{type:'array',minItems:1,maxItems:64,items:shape({op:{type:'string',enum:OPERATIONS},uuid:{type:'string'},name:{type:'string'},from:vectorSchema,to:vectorSchema,origin:vectorSchema,rotation:vectorSchema,visible:{type:'boolean'},uv_offset:{type:'array',items:{type:'integer'},minItems:2,maxItems:2},inflate:{type:'number'},mirror:{type:'boolean'},uv_faces:uvFacesSchema,vertices:{type:'object'},faces:{type:'object'},group_uuid:{type:'string'},parent_group_uuid:{type:'string'}},['op'])}},['file','expected_revision','operations']),true),
  spec('bbmodel_geckolib_create','Create Blockbench 5.x geckolib_model project (Entity/Block/Item/Armor/Object). No overwrite. Set identifier, modid, texture size.',
    shape({file:fileSchema,name:{type:'string'},identifier:{type:'string'},modid:{type:'string'},model_type:{type:'string',enum:['Entity','Block','Item','Armor','Object']},texture_width:{type:'integer'},texture_height:{type:'integer'}},['file','identifier','modid']),true),
  spec('bbmodel_geckolib_upsert_animation','Write numeric bone keyframes with allowlisted interpolation. Requires exact SHA-256 revision. Rejects invalid loops and unknown bones.',shape({file:fileSchema,expected_revision:{type:'string'},name:{type:'string'},length:{type:'number'},loop:{type:'string',enum:['once','loop','hold']},replace:{type:'boolean'},replace_tracks:{type:'boolean'},channels:{type:'array',items:channelSchema}},['file','expected_revision','name','length','channels']),true),
  spec('bbmodel_geckolib_validate','Validate GeckoLib rules, hierarchy, UVs, animation names, timestamps, numeric keyframes and loop seams.',shape({file:fileSchema,require_idle_walk:{type:'boolean'},required_animations:{type:'array',items:{type:'string'},maxItems:24}},['file'])),
  spec('bbmodel_geckolib_export_geometry','Compile GeckoLib geometry JSON 1.12.0. Optional output_file creates *.geo.json (overwrite explicitly opt-in) only inside workspace (requires --allow-write).',shape({file:fileSchema,output_file:{type:'string'},overwrite:{type:'boolean'}},['file'])),
  spec('bbmodel_geckolib_export_animations','Compile GeckoLib animation JSON 1.8.0 + geckolib_format_version=2. Optional output_file creates *.animation.json (overwrite explicitly opt-in) (requires --allow-write).',shape({file:fileSchema,output_file:{type:'string'},overwrite:{type:'boolean'}},['file'])),
  spec('bbmodel_geckolib_set_texture','Embed a validated workspace PNG (the model resolution or a uniform integer multiple of it, e.g. 128x128 over a 64x64 UV layout), and assign its texture UUID to all existing cube faces. Requires --allow-write and expected_revision.',shape({file:fileSchema,expected_revision:{type:'string'},png_file:{type:'string'}},['file','expected_revision','png_file']),true),
  spec('bbmodel_geckolib_remove_animation','Remove a complete animation clip. Requires exact revision and --allow-write.',shape({file:fileSchema,expected_revision:{type:'string'},name:{type:'string'}},['file','expected_revision','name']),true),
  spec('bbmodel_geckolib_remove_track','Remove one bone/channel track from an animation clip. Requires exact revision and --allow-write.',shape({file:fileSchema,expected_revision:{type:'string'},name:{type:'string'},bone:{type:'string'},channel:{type:'string',enum:['rotation','position','scale']}},['file','expected_revision','name','bone','channel']),true),
  spec('bbmodel_geckolib_read_scene','Read concise hierarchical bone/cube scene and animation track summary.',shape({file:fileSchema},['file'])),
  spec('bbmodel_duplicate','Copy existing .bbmodel under a new name inside workspace; never overwrites. Requires --allow-write.',shape({file:fileSchema,new_file:fileSchema},['file','new_file']),true)
];

function argsObject(args) {
  if (args === undefined) return {};
  if (args === null || Array.isArray(args) || typeof args !== 'object') throw new Error('Arguments must be a JSON object');
  return args;
}
function rejectUnknown(obj, allowed) {
  for (const key of Object.keys(obj)) if (!allowed.includes(key)) throw new Error(`Unexpected argument: ${key}. Valid fields: ${allowed.join(', ')}`);
}
function requireWrite(enabled) { if (!enabled) throw new Error('Write access disabled; restart explicitly with --allow-write to enable'); }
function json(model) { return `${JSON.stringify(model,null,2)}\n`; }

export async function runTool(store, allowWrite, toolName, unsafeArgs, liveEnabled=false) {
  const args = argsObject(unsafeArgs);
  const t = TOOLS.find(t=>t.name===toolName);
  if (!t) throw new Error('Unknown tool');
  rejectUnknown(args,Object.keys(t.inputSchema.properties));
  for (const k of t.inputSchema.required || []) if (args[k] === undefined) throw new Error(`Missing required argument: ${k}`);
  if (t.writes) requireWrite(allowWrite);
  if(t.live){
    if(!liveEnabled)throw Error('Live tools disabled; launch MCP with --enable-live and connect the optional Blockbench bridge manually');
    const response=await readLive(store,toolName);
    if(toolName==='app_capture_screenshot'){const image=response.png;delete response.png;return {...response,__mcpImage:image};}
    return response;
  }
  if (toolName === 'bbmodel_list_files') return {files:await listFiles(store)};
  if (toolName === 'bbmodel_create') {
    filename(args.file);
    const name = args.name === undefined ? args.file.slice(0,-8) : args.name;
    const model = createModel(name,args.texture_width,args.texture_height);
    const rev = await saveNew(store,args.file,json(model));
    return {created:args.file,revision:rev,model:overview(model)};
  }
  if (toolName === 'bbmodel_geckolib_create') {
    filename(args.file);
    const model=createGeckoModel({name:args.name??args.file.slice(0,-8),identifier:args.identifier,modid:args.modid,model_type:args.model_type,texture_width:args.texture_width,texture_height:args.texture_height});
    const rev=await saveNew(store,args.file,json(model));
    return {created:args.file,revision:rev,model:overview(model)};
  }
  if (toolName === 'bbmodel_duplicate') {
    filename(args.file);filename(args.new_file);
    const original = await readRaw(store,args.file);
    parseModel(original.raw);
    const rev = await saveNew(store,args.new_file,original.raw);
    return {created:args.new_file,revision:rev};
  }
  filename(args.file);
  const current = await readRaw(store,args.file);
  const model = parseModel(current.raw);
  if(toolName==='bbmodel_sample_pose')return {...samplePose(model,args),file:args.file,revision:current.revision};
  if(toolName==='bbmodel_quality_gates'){
    const {file,...options}=args;return {...validateQuality(model,options),file,revision:current.revision};
  }
  if(toolName==='bbmodel_render'){
    const rendered=renderModel(model,args);
    // JSON/base64 MCP response is capped at 1 MiB; keep image content well below it.
    const includeImage=rendered.png.length<=600*1024;
    if(!includeImage&&args.output_file===undefined)throw Error('Preview PNG exceeds MCP image response budget; reduce size/views or supply output_file with --allow-write');
    const output={file:args.file,revision:current.revision,width:rendered.width,height:rendered.height,views:rendered.views,triangles:rendered.triangles,texture_applied:rendered.texture_applied,animation:rendered.animation,sampled_time:rendered.sampled_time,render_mode:rendered.render_mode};
    if(args.output_file!==undefined){requireWrite(allowWrite);Object.assign(output,await savePreview(store,args.output_file,rendered.png,args.overwrite??false));}
    else if(args.overwrite!==undefined)throw Error('overwrite requires output_file');
    return {...output,image_omitted:!includeImage,...(includeImage?{__mcpImage:rendered.png.toString('base64')}:{})};
  }
  if (toolName === 'bbmodel_info') return {...overview(model),file:args.file,revision:current.revision};
  if (toolName === 'bbmodel_geckolib_read_scene') return {...readGeckoScene(model),file:args.file,revision:current.revision};
  if (toolName === 'bbmodel_read_scene') return {...overview(model,true),file:args.file,revision:current.revision};
  if (toolName === 'bbmodel_validate') return {...inspect(model),file:args.file,revision:current.revision};
  if (toolName === 'bbmodel_geckolib_validate') {
    const result=validateGecko(model);
    if(args.require_idle_walk!==undefined && typeof args.require_idle_walk!=='boolean') throw new Error('require_idle_walk must be boolean');
    if(args.require_idle_walk===true) {
      const names=new Set((model.animations||[]).map(a=>a.name));
      for(const suffix of ['idle','walk'])if(![...names].some(name=>name.endsWith('.'+suffix)))result.errors.push('REQUIRED_ANIMATION_MISSING: animation ending in .'+suffix);
      result.valid=result.errors.length===0;
    }
    if(args.required_animations!==undefined) {
      if(!Array.isArray(args.required_animations) || args.required_animations.length>24 || args.required_animations.some(x=>typeof x!=='string')) throw new Error('Invalid required_animations');
      const existing=new Set((model.animations||[]).map(x=>x.name));
      for(const name of args.required_animations) if(!existing.has(name)) result.errors.push('REQUIRED_ANIMATION_MISSING: '+name);
      result.valid=result.errors.length===0;
    }
    return {...result,file:args.file,revision:current.revision};
  }
  if (toolName === 'bbmodel_geckolib_export_geometry' || toolName === 'bbmodel_geckolib_export_animations') {
    const isGeometry=toolName==='bbmodel_geckolib_export_geometry';
    const data=isGeometry?exportGeometry(model):exportAnimations(model);
    if (args.output_file!==undefined) {
      requireWrite(allowWrite);
      const saved=await saveExport(store,args.output_file,json(data),isGeometry?'geo':'animation',args.overwrite??false);
      return {...saved,file:args.output_file,revision:saved.sha256,source_revision:current.revision,kind:isGeometry?'geometry':'animations'};
    }
    if(args.overwrite!==undefined && typeof args.overwrite!=='boolean')throw new Error('overwrite must be boolean');
    if(args.overwrite===true && args.output_file===undefined)throw new Error('overwrite requires output_file');
    return {kind:isGeometry?'geometry':'animations',source_revision:current.revision,output:data};
  }
  if (toolName === 'bbmodel_geckolib_set_texture') {
    if(model.meta.model_format!=='geckolib_model')throw new Error('Texture tool requires geckolib_model');
    if(typeof args.expected_revision!=='string')throw new Error('expected_revision is required');
    const buf=await readWorkspacePng(store,args.png_file);
    const change=embedTexture(model,buf,args.png_file);
    const validated=validateGecko(model);
    if(!validated.valid)throw new Error('GeckoLib texture rejected: '+validated.errors[0]);
    const rev=await saveExisting(store,args.file,json(model),args.expected_revision);
    return {file:args.file,revision:rev,change};
  }
  if (toolName === 'bbmodel_geckolib_remove_animation' || toolName === 'bbmodel_geckolib_remove_track') {
    const change=toolName==='bbmodel_geckolib_remove_animation'?removeAnimation(model,args.name):removeAnimationTrack(model,args.name,args.bone,args.channel);
    const rev=await saveExisting(store,args.file,json(model),args.expected_revision);
    return {file:args.file,revision:rev,change};
  }
  if (toolName === 'bbmodel_geckolib_upsert_animation') {
    const changes=upsertAnimation(model,args);
    const rev=await saveExisting(store,args.file,json(model),args.expected_revision);
    return {file:args.file,revision:rev,changes};
  }
  if (toolName === 'bbmodel_edit') {
    if (typeof args.expected_revision !== 'string') throw new Error('expected_revision required');
    if (!Array.isArray(args.operations)) throw new Error('operations must be an array');
    for (const op of args.operations) {
      if (!op || Array.isArray(op) || typeof op !== 'object') throw new Error('Invalid edit operation');
      rejectUnknown(op,['op','uuid','name','from','to','origin','rotation','visible','group_uuid','parent_group_uuid','uv_offset','inflate','mirror','uv_faces','vertices','faces']);
    }
    const changes = editModel(model,args.operations);
    if(model.meta.model_format==='geckolib_model') {
      const validation=validateGecko(model);
      if(!validation.valid) throw new Error('GeckoLib edit rejected: '+validation.errors[0]);
    }
    const rev = await saveExisting(store,args.file,json(model),args.expected_revision);
    return {file:args.file,revision:rev,changes,model:overview(model)};
  }
  throw new Error('Unsupported tool');
}
