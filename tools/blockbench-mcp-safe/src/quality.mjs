import {inspect} from './model.mjs';
import {validateGecko} from './geckolib.mjs';
const isNum=x=>typeof x==='number'&&Number.isFinite(x);
import {gaitWarnings} from './gait.mjs';
export function validateQuality(model,opts={}){
  const defaults={max_span:48,max_axis_ratio:12,max_cubes:256,max_bones:96,min_thickness:0.1,max_bone_depth:16,fail_on_warnings:false};
  for(const [k,v] of Object.entries(opts)){
    if(!(k in defaults))throw Error('Invalid quality gate: '+k+'; valid: '+Object.keys(defaults).join(', '));
    if(k==='fail_on_warnings'){if(typeof v!=='boolean')throw Error(k+' must be boolean');}
    else if(!isNum(v)||v<=0||v>100000)throw Error(k+' must be positive finite <=100000');
  }
  const p={...defaults,...opts};
  const base=model.meta?.model_format==='geckolib_model'?validateGecko(model):inspect(model);
  const errors=[...base.errors],warnings=[...base.warnings];
  const cubes=model.elements.filter(e=>(e.type==='cube'||e.type===undefined)&&Array.isArray(e.from)&&Array.isArray(e.to));
  if(cubes.length>p.max_cubes)errors.push(`CUBE_COUNT_LIMIT: ${cubes.length} > ${p.max_cubes}`);
  if((model.groups||[]).length>p.max_bones)errors.push(`BONE_COUNT_LIMIT: ${model.groups.length} > ${p.max_bones}`);
  const min=[Infinity,Infinity,Infinity],max=[-Infinity,-Infinity,-Infinity];
  for(const c of cubes){
    const dims=c.from.map((v,i)=>c.to[i]-v);
    if(!dims.every(d=>isNum(d)&&d>0)){errors.push('INVALID_DIMENSIONS: '+(c.name||c.uuid));continue;}
    const ratio=Math.max(...dims)/Math.min(...dims);
    if(ratio>p.max_axis_ratio)errors.push(`EXTREME_PROPORTION: ${c.name} axis ratio ${ratio.toFixed(2)} > ${p.max_axis_ratio}`);
    if(Math.min(...dims)<p.min_thickness)warnings.push(`THIN_GEOMETRY: ${c.name} thickness ${Math.min(...dims).toFixed(3)}`);
    for(let i=0;i<3;i++){min[i]=Math.min(min[i],c.from[i]);max[i]=Math.max(max[i],c.to[i]);}
  }
  const spans=cubes.length?max.map((v,i)=>v-min[i]):[0,0,0];
  for(let i=0;i<3;i++)if(spans[i]>p.max_span)errors.push(`BOUNDS_EXCEEDED: ${['X','Y','Z'][i]} span ${spans[i]} > ${p.max_span}`);
  const groups=new Set((model.groups||[]).map(x=>x.uuid));
  const walk=(nodes,depth)=>{for(const n of nodes){if(typeof n==='string')continue;if(groups.has(n.uuid)&&depth>p.max_bone_depth)errors.push(`RIG_TOO_DEEP: ${n.uuid} depth ${depth}`);if(depth<=32&&Array.isArray(n.children))walk(n.children,depth+1);}};
  walk(model.outliner,1);
  if(model.meta?.model_format==='geckolib_model'){try{warnings.push(...gaitWarnings(model));}catch(e){/* gait is advisory; a malformed clip is reported by the other gates */}}
  return {valid:errors.length===0&&(!p.fail_on_warnings||warnings.length===0),errors:errors.slice(0,100),warnings:warnings.slice(0,100),metrics:{cubes:cubes.length,bones:model.groups?.length||0,span:spans},gates:p};
}
