// Pure JS (Node built-ins only) PNG to RGBA decoder for the controlled renderer.
// No native image codecs, filesystem access, network, dynamic code, or unbounded inflate.
import {inflateSync} from 'node:zlib';
import {pngSize} from './png.mjs';

const channelsByType={0:1,2:3,3:1,4:2,6:4};
const paeth=(a,b,c)=>{const p=a+b-c,pa=Math.abs(p-a),pb=Math.abs(p-b),pc=Math.abs(p-c);return pa<=pb&&pa<=pc?a:pb<=pc?b:c;};
export function decodePngRGBA(buffer){
  const {width,height}=pngSize(buffer); // signature, CRC, chunk structure, max inflated bytes and filters
  let depth,color,palette=null,transparency=null;
  const idat=[];
  for(let offset=8;offset<buffer.length;){
    const length=buffer.readUInt32BE(offset),type=buffer.toString('ascii',offset+4,offset+8);
    const payload=buffer.subarray(offset+8,offset+8+length);
    if(type==='IHDR'){depth=payload[8];color=payload[9];}
    else if(type==='PLTE'){
      if(length===0||length>768||length%3!==0)throw Error('Invalid PNG palette');
      palette=payload;
    }else if(type==='tRNS'){
      if(length>256)throw Error('Invalid PNG transparency');
      transparency=payload;
    }else if(type==='IDAT')idat.push(payload);
    offset+=length+12;
  }
  if(![1,2,4,8].includes(depth)||(![0,3].includes(color)&&depth!==8))throw Error('Texture preview only supports PNG 8-bit RGB/RGBA/gray-alpha or 1/2/4/8-bit gray/indexed PNG; 16-bit PNG unsupported');
  if(color===3&&(!palette||palette.length/3>2**depth))throw Error('PNG indexed color requires matching palette');
  if(transparency && color===3 && transparency.length>palette.length/3)throw Error('Invalid PNG indexed transparency');
  if(transparency && ![0,2,3].includes(color))throw Error('Unexpected PNG transparency chunk');
  if(transparency && color===0 && transparency.length!==2)throw Error('Invalid grayscale transparency chunk');
  if(transparency && color===2 && transparency.length!==6)throw Error('Invalid truecolor transparency chunk');
  const channel=channelsByType[color];
  const stride=Math.ceil(width*channel*depth/8),bpp=Math.max(1,Math.ceil(channel*depth/8));
  const expected=(stride+1)*height;
  const raw=inflateSync(Buffer.concat(idat),{maxOutputLength:expected+1});
  if(raw.length!==expected)throw Error('PNG decoded bytes do not match dimensions');
  const out=Buffer.alloc(width*height*4);
  let prev=Buffer.alloc(stride),pos=0;
  for(let y=0;y<height;y++){
    const filter=raw[pos++],row=Buffer.from(raw.subarray(pos,pos+stride));pos+=stride;
    for(let i=0;i<stride;i++){
      const a=i>=bpp?row[i-bpp]:0,b=prev[i],c=i>=bpp?prev[i-bpp]:0;
      const predict=[0,a,b,Math.floor((a+b)/2),paeth(a,b,c)][filter];
      if(predict===undefined)throw Error('Unsupported PNG filter');
      row[i]=(row[i]+predict)&255;
    }
    for(let x=0;x<width;x++){
      const oi=(y*width+x)*4;
      if(color===6){const i=x*4;out[oi]=row[i];out[oi+1]=row[i+1];out[oi+2]=row[i+2];out[oi+3]=row[i+3];}
      else if(color===2){const i=x*3;out[oi]=row[i];out[oi+1]=row[i+1];out[oi+2]=row[i+2];out[oi+3]=transparency&&row[i]===transparency[1]&&row[i+1]===transparency[3]&&row[i+2]===transparency[5]?0:255;}
      else if(color===4){const i=x*2;out[oi]=out[oi+1]=out[oi+2]=row[i];out[oi+3]=row[i+1];}
      else {
        const mask=(1<<depth)-1,index=depth===8?row[x]:(row[Math.floor(x*depth/8)]>>(8-depth-(x*depth%8)))&mask;
        if(color===3){if(index>=palette.length/3)throw Error('PNG palette index out of range');const j=index*3;out[oi]=palette[j];out[oi+1]=palette[j+1];out[oi+2]=palette[j+2];out[oi+3]=transparency?.[index]??255;}
        else {const gray=Math.round(index*255/mask);out[oi]=out[oi+1]=out[oi+2]=gray;out[oi+3]=transparency && index===transparency.readUInt16BE(0)?0:255;}
      }
    }
    prev=row;
  }
  return {width,height,pixels:out};
}
export function textureFromModel(model){
  if(!Array.isArray(model.textures)||model.textures.length===0)return null;
  if(model.textures.length!==1)throw Error('Preview supports exactly one embedded PNG texture; remove additional textures or render with textures:false');
  const texture=model.textures[0];
  if(typeof texture?.source!=='string'||!/^data:image\/png;base64,[A-Za-z0-9+/=]+$/.test(texture.source))throw Error('Preview requires an embedded PNG texture; external texture paths are not loaded');
  const encoded=texture.source.slice('data:image/png;base64,'.length);
  if(encoded.length>3*1024*1024)throw Error('Embedded PNG exceeds preview size limit');
  const decoded=decodePngRGBA(Buffer.from(encoded,'base64'));
  const scale=decoded.width/(model.resolution?.width||1);
  if(!Number.isInteger(scale)||scale<1||decoded.height!==model.resolution?.height*scale)throw Error('Embedded texture is not the model resolution or a uniform integer multiple of it');
  return {...decoded,scale,uuid:texture.uuid};
}
