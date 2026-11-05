// Deterministic, software rasterized PNG/contact-sheet renderer, Node built-ins only.
// Supports embedded texture UVs, cube/mesh transforms and hierarchical GeckoLib bone poses.
// This is an approximation of the Blockbench viewport, NOT a GPU or in-game renderer.
import zlib from 'node:zlib';
import {samplePose} from './pose.mjs';
import {textureFromModel} from './texture-render.mjs';

const angles={front:[0,0],back:[180,0],left:[-90,0],right:[90,0],top:[0,90],iso:[45,27]};
// Cube faces as Blockbench builds them (the vertex order of three.js BoxGeometry): top-left, top-right, bottom-right, bottom-left as seen from OUTSIDE
// the face. For up the top edge is the north side; for down it is the south side. `lo` and `hi` are the min and max corners.
export function cubeQuads(lo,hi){
  return {
    north:[[hi[0],hi[1],lo[2]],[lo[0],hi[1],lo[2]],[lo[0],lo[1],lo[2]],[hi[0],lo[1],lo[2]]],
    south:[[lo[0],hi[1],hi[2]],[hi[0],hi[1],hi[2]],[hi[0],lo[1],hi[2]],[lo[0],lo[1],hi[2]]],
    east:[[hi[0],hi[1],hi[2]],[hi[0],hi[1],lo[2]],[hi[0],lo[1],lo[2]],[hi[0],lo[1],hi[2]]],
    west:[[lo[0],hi[1],lo[2]],[lo[0],hi[1],hi[2]],[lo[0],lo[1],hi[2]],[lo[0],lo[1],lo[2]]],
    up:[[lo[0],hi[1],lo[2]],[hi[0],hi[1],lo[2]],[hi[0],hi[1],hi[2]],[lo[0],hi[1],hi[2]]],
    down:[[lo[0],lo[1],hi[2]],[hi[0],lo[1],hi[2]],[hi[0],lo[1],lo[2]],[lo[0],lo[1],lo[2]]]
  };
}
const finite=x=>typeof x==='number'&&Number.isFinite(x)&&Math.abs(x)<=1000000;
const vec3=x=>Array.isArray(x)&&x.length===3&&x.every(finite);
const sub=(a,b)=>a.map((v,i)=>v-b[i]);
const cross=(a,b)=>[a[1]*b[2]-a[2]*b[1],a[2]*b[0]-a[0]*b[2],a[0]*b[1]-a[1]*b[0]];
const safeVec=(x,defaultValue,label)=>{if(x===undefined)return defaultValue;if(!vec3(x))throw Error(`Invalid ${label} transform for preview`);return x;};
const radians=x=>x*Math.PI/180;
function rotateEuler(v,degrees){
  const [rx,ry,rz]=degrees.map(radians);
  const [sx,cx]=[Math.sin(rx),Math.cos(rx)],[sy,cy]=[Math.sin(ry),Math.cos(ry)],[sz,cz]=[Math.sin(rz),Math.cos(rz)];
  const x=[v[0],v[1]*cx-v[2]*sx,v[1]*sx+v[2]*cx];
  const y=[x[0]*cy+x[2]*sy,x[1],-x[0]*sy+x[2]*cy];
  return [y[0]*cz-y[1]*sz,y[0]*sz+y[1]*cz,y[2]];
}
function around(point,pivot,rotation,scale=[1,1,1],translation=[0,0,0]){
  const p=rotateEuler(point.map((v,i)=>(v-pivot[i])*scale[i]),rotation);
  return p.map((v,i)=>v+pivot[i]+translation[i]);
}
function viewRotate(v,yaw,pitch){
  const y=radians(yaw),p=radians(pitch);
  const q=[v[0]*Math.cos(y)+v[2]*Math.sin(y),v[1],-v[0]*Math.sin(y)+v[2]*Math.cos(y)];
  return [q[0],q[1]*Math.cos(p)-q[2]*Math.sin(p),q[1]*Math.sin(p)+q[2]*Math.cos(p)];
}
export function boxUvs(c,side){
  const [u,v]=Array.isArray(c.uv_offset)?c.uv_offset:[0,0];
  const fl=n=>Math.floor(n+1e-6);
  const w=fl(c.to[0]-c.from[0]),h=fl(c.to[1]-c.from[1]),d=fl(c.to[2]-c.from[2]);
  // [u1,v1,u2,v2] with (u1,v1) at the top-left of the face seen from outside; Blockbench stores up as [d+w,d,d,0] and down as [d+2w,0,d+w,d] (reversed).
  const rectangles={
    east:[u,v+d,u+d,v+d+h],north:[u+d,v+d,u+d+w,v+d+h],
    west:[u+d+w,v+d,u+2*d+w,v+d+h],south:[u+2*d+w,v+d,u+2*d+2*w,v+d+h],
    up:[u+d+w,v+d,u+d,v],down:[u+d+2*w,v,u+d+w,v+d]
  };
  return rectangles[side];
}
function uvPoints(rect,rotation=0,mirror=false){
  if(!Array.isArray(rect)||rect.length!==4||rect.some(x=>!finite(x)))throw Error('Invalid texture UV rectangle');
  if(![0,90,180,270].includes(rotation))throw Error('Unsupported UV rotation; expected 0, 90, 180, 270');
  const [u0,v0,u1,v1]=rect;
  const midU=(u0+u1)/2,midV=(v0+v1)/2;
  return [[u0,v0],[u1,v0],[u1,v1],[u0,v1]].map(([u,v])=>{
    if(mirror)u=u0+u1-u;
    const du=u-midU,dv=v-midV;
    if(rotation===90)return [midU-dv,midV+du];
    if(rotation===180)return [midU-du,midV-dv];
    if(rotation===270)return [midU+dv,midV-du];
    return [u,v];
  });
}
function buildTriangles(model,pose){
  if(!Array.isArray(model.elements))throw Error('Preview requires elements[] array');
  // Allow empty renderer previews used by the optional read-only desktop bridge.
  const outliner=Array.isArray(model.outliner)?model.outliner:[];
  const modelGroups=Array.isArray(model.groups)?model.groups:[];
  if(model.elements.length>1200||modelGroups.length>400)throw Error('Preview scene is too large');
  const byUuid=new Map(model.elements.map(e=>[e.uuid,e]));
  const groups=new Map(modelGroups.map(g=>[g.uuid,g]));
  const poseByUuid=new Map((pose?.bones||[]).map(b=>[b.uuid,b]));
  const tris=[];
  const seen=new Set();
  function makeElement(e,ancestors){
    if(!e||e.visibility===false||e.export===false)return;
    const pivot=safeVec(e.origin,[0,0,0],'cube/mesh origin');
    const eRotation=safeVec(e.rotation,[0,0,0],'cube/mesh rotation');
    const transform=point=>{
      let p=around(point,pivot,eRotation);
      // Each bone operates on the entire subtree; child bone first, root last.
      for(let i=ancestors.length-1;i>=0;i--){
        const g=ancestors[i],s=poseByUuid.get(g.uuid);
        const gOrigin=safeVec(g.origin,[0,0,0],'bone origin');
        const rest=safeVec(g.rotation,[0,0,0],'bone rotation');
        const anim=safeVec(s?.rotation,[0,0,0],'animated rotation');
        const translation=safeVec(s?.position,[0,0,0],'animated position');
        const scale=safeVec(s?.scale,[1,1,1],'animated scale');
        p=around(p,gOrigin,rest.map((v,j)=>v+anim[j]),scale,translation);
      }
      if(!p.every(finite))throw Error('Preview geometry has invalid transformed coordinates');
      return p;
    };
    const emit=(verts,uvs,usesTexture)=>{
      const indices=[[0,1,2],[0,2,3]];
      for(const ids of (verts.length===3?[indices[0]]:indices)){
        const vertices=ids.map(i=>transform(verts[i]));
        const coords=ids.map(i=>uvs?.[i]??null);
        tris.push({vertices,uvs:coords,textured:Boolean(usesTexture&&uvs)});
      }
      if(tris.length>450)throw Error('Preview geometry exceeds 450 triangles; render a smaller model');
    };
    if(e.type==='mesh'){
      // Generic meshes: UVs are attached to face corners; supports triangles and quads.
      for(const face of Object.values(e.faces||{})){
        if(!Array.isArray(face.vertices)||![3,4].includes(face.vertices.length))continue;
        const verts=face.vertices.map(k=>e.vertices?.[k]);
        if(verts.some(x=>!vec3(x)))throw Error('Invalid mesh vertex in preview');
        const uvs=face.vertices.map(k=>face.uv?.[k]);
        if(uvs.some(x=>!Array.isArray(x)||x.length!==2||x.some(n=>!finite(n))))throw Error('Invalid mesh UV in preview');
        emit(verts,uvs,true);
      }
    }else if(e.type==='cube'||e.type===undefined){
      const a=e.from,b=e.to;
      if(!vec3(a)||!vec3(b)||a.some((v,i)=>v>=b[i]))throw Error('Invalid cube coordinates for preview');
      const inflate=finite(e.inflate??0)?e.inflate??0:0;
      const x=a.map(v=>v-inflate),z=b.map(v=>v+inflate);
      if(x.some((v,i)=>v>=z[i]))throw Error('Cube inflation inverts geometry');
      for(const [side,quad] of Object.entries(cubeQuads(x,z))){
        const face=e.faces?.[side];
        // Untextured cubes default to six visible gray faces. Per-face null texture means disabled.
        if(e.box_uv===false&&(!face||face.texture===null))continue;
        const uvSide=(e.box_uv!==false&&e.mirror_uv===true)?({east:'west',west:'east'}[side]??side):side;   // mirror_uv swaps the east and west rectangles
        const rect=e.box_uv===false?face?.uv:boxUvs(e,uvSide);
        const uvs=rect?uvPoints(rect,face?.rotation??0,e.mirror_uv===true):null;
        emit(quad,uvs,true);
      }
    }
  }
  const walk=(nodes,ancestors,depth)=>{
    if(depth>64)throw Error('Outliner exceeds maximum preview depth');
    if(!Array.isArray(nodes))throw Error('Invalid outliner children');
    for(const node of nodes){
      if(typeof node==='string'){
        if(seen.has(node))continue;
        seen.add(node);
        makeElement(byUuid.get(node),ancestors);
      }else if(node&&typeof node==='object'&&typeof node.uuid==='string'){
        if(!groups.has(node.uuid))continue;
        if(ancestors.some(g=>g.uuid===node.uuid))throw Error('Cyclic bone hierarchy');
        walk(node.children??[],[...ancestors,groups.get(node.uuid)],depth+1);
      }
    }
  };
  walk(outliner,[],0);
  // Models imported with loose/outliner-omitted elements remain inspectable.
  for(const e of model.elements)if(!seen.has(e.uuid))makeElement(e,[]);
  return tris;
}
function put32(b,i,v){b.writeUInt32BE(v>>>0,i);}
const crcTable=Array.from({length:256},(_,i)=>{let c=i;for(let k=0;k<8;k++)c=c&1?0xedb88320^(c>>>1):c>>>1;return c>>>0;});
function crc(buf){let c=0xffffffff;for(const b of buf)c=crcTable[(c^b)&255]^(c>>>8);return (c^0xffffffff)>>>0;}
function chunk(type,body){const raw=Buffer.concat([Buffer.from(type),body]),out=Buffer.alloc(raw.length+8);put32(out,0,body.length);raw.copy(out,4);put32(out,raw.length+4,crc(raw));return out;}
export function encodePng(pixels,width,height){
  if(!Buffer.isBuffer(pixels)||pixels.length!==width*height*4||width<1||height<1||width*height>1024*1024)throw Error('Invalid render PNG pixels');
  const scan=Buffer.alloc(height*(1+width*4));
  for(let y=0;y<height;y++){const dst=y*(width*4+1);scan[dst]=0;pixels.copy(scan,dst+1,y*width*4,(y+1)*width*4);}
  const header=Buffer.alloc(13);put32(header,0,width);put32(header,4,height);header[8]=8;header[9]=6;
  return Buffer.concat([Buffer.from([137,80,78,71,13,10,26,10]),chunk('IHDR',header),chunk('IDAT',zlib.deflateSync(scan,{level:8})),chunk('IEND',Buffer.alloc(0))]);
}
function shade(normal){const unit=Math.hypot(...normal)||1;const light=Math.abs((normal[0]*.3+normal[1]*.75+normal[2]*.58)/unit);return .52+.46*light;}
function draw(tris,view,size,texture){
  const width=size,height=size,bg=[25,32,45,255],pixels=Buffer.alloc(width*height*4),depth=new Float64Array(width*height).fill(-Infinity);
  for(let i=0;i<pixels.length;i+=4){pixels[i]=bg[0];pixels[i+1]=bg[1];pixels[i+2]=bg[2];pixels[i+3]=255;}
  if(!tris.length)return pixels;
  const [yaw,pitch]=angles[view],transformed=tris.map(t=>t.vertices.map(v=>viewRotate(v,yaw,pitch)));
  let xmin=Infinity,xmax=-Infinity,ymin=Infinity,ymax=-Infinity;
  for(const t of transformed)for(const p of t){xmin=Math.min(xmin,p[0]);xmax=Math.max(xmax,p[0]);ymin=Math.min(ymin,p[1]);ymax=Math.max(ymax,p[1]);}
  const midx=(xmin+xmax)/2,midy=(ymin+ymax)/2;
  const scale=Math.min((size-20)/(xmax-xmin||1),(size-20)/(ymax-ymin||1));
  const project=v=>[(v[0]-midx)*scale+width/2,height/2-(v[1]-midy)*scale,v[2]];
  for(let i=0;i<tris.length;i++){
    const [a,b,c]=transformed[i].map(project),tri=tris[i];
    const det=(b[1]-c[1])*(a[0]-c[0])+(c[0]-b[0])*(a[1]-c[1]);
    if(Math.abs(det)<1e-10)continue;
    const normal=cross(sub(transformed[i][1],transformed[i][0]),sub(transformed[i][2],transformed[i][0]));
    const light=shade(normal);
    const x0=Math.max(0,Math.floor(Math.min(a[0],b[0],c[0]))),x1=Math.min(width-1,Math.ceil(Math.max(a[0],b[0],c[0])));
    const y0=Math.max(0,Math.floor(Math.min(a[1],b[1],c[1]))),y1=Math.min(height-1,Math.ceil(Math.max(a[1],b[1],c[1])));
    for(let y=y0;y<=y1;y++)for(let x=x0;x<=x1;x++){
      const p=x+.5,q=y+.5;
      const wa=((b[1]-c[1])*(p-c[0])+(c[0]-b[0])*(q-c[1]))/det;
      const wb=((c[1]-a[1])*(p-c[0])+(a[0]-c[0])*(q-c[1]))/det;
      const wc=1-wa-wb;
      if(wa<-1e-7||wb<-1e-7||wc<-1e-7)continue;
      const z=wa*a[2]+wb*b[2]+wc*c[2],idx=y*width+x;
      if(z<depth[idx])continue;
      let r=105,g=182,bl=211,alpha=255;
      if(texture&&tri.textured&&tri.uvs.every(uv=>uv!==null)){
        const u=wa*tri.uvs[0][0]+wb*tri.uvs[1][0]+wc*tri.uvs[2][0];
        const v=wa*tri.uvs[0][1]+wb*tri.uvs[1][1]+wc*tri.uvs[2][1];
        const tu=u*(texture.scale||1),tv=v*(texture.scale||1);
        if(tu<0||tu>=texture.width||tv<0||tv>=texture.height)continue;
        const si=(Math.floor(tv)*texture.width+Math.floor(tu))*4;
        r=texture.pixels[si];g=texture.pixels[si+1];bl=texture.pixels[si+2];alpha=texture.pixels[si+3];
      }
      if(alpha===0)continue;
      const off=idx*4,t=alpha/255;
      pixels[off]=Math.round(r*light*t+pixels[off]*(1-t));
      pixels[off+1]=Math.round(g*light*t+pixels[off+1]*(1-t));
      pixels[off+2]=Math.round(bl*light*t+pixels[off+2]*(1-t));
      pixels[off+3]=255;
      depth[idx]=z;
    }
  }
  return pixels;
}
export function renderModel(model,{views=['front','right','back','iso'],size=160,textures=true,animation,time=0,wrap=true}={}){
  if(!Array.isArray(views)||views.length<1||views.length>6||views.some(v=>!Object.hasOwn(angles,v)))throw Error('views must be 1..6 of front, back, left, right, top, iso');
  if(!Number.isInteger(size)||size<64||size>320)throw Error('size must be an integer 64..320');
  if(typeof textures!=='boolean'||typeof wrap!=='boolean')throw Error('textures and wrap must be boolean');
  if(animation!==undefined&&(typeof animation!=='string'||!animation))throw Error('animation must be a nonempty clip name');
  if(!Number.isFinite(time)||time<0||time>600000)throw Error('time must be a finite value >=0 and <=600000 seconds');
  if(animation===undefined&&time!==0)throw Error('time requires an animation');
  const pose=animation===undefined?null:samplePose(model,{animation,time,wrap});
  const texture=textures?textureFromModel(model):null;
  const tris=buildTriangles(model,pose);
  const cols=Math.min(2,views.length),rows=Math.ceil(views.length/cols),w=cols*size,h=rows*size;
  const pixels=Buffer.alloc(w*h*4,255);
  for(let i=0;i<views.length;i++){
    const tile=draw(tris,views[i],size,texture),ox=(i%cols)*size,oy=Math.floor(i/cols)*size;
    for(let y=0;y<size;y++)tile.copy(pixels,((oy+y)*w+ox)*4,y*size*4,(y+1)*size*4);
  }
  return {png:encodePng(pixels,w,h),views,width:w,height:h,triangles:tris.length,texture_applied:!!texture,
    animation:pose?.animation??null,sampled_time:pose?.sampled_time??null,
    render_mode:'CPU software textured orthographic preview; supports box/per-face UV and hierarchical bone + cube Euler transforms; no GPU, PBR, Molang, or exact Blockbench renderer parity'};
}
