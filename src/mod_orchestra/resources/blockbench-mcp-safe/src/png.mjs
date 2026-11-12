// Decode PNG container metadata only; never execute pixel decoders, native libraries or subprocesses.
import {randomUUID} from 'node:crypto';
import {inflateSync} from 'node:zlib';

function fail(message) {throw new Error(message);}
const SIGNATURE=Buffer.from('89504e470d0a1a0a','hex');
const crcTable=new Uint32Array(256);
for(let i=0;i<256;i++){let c=i;for(let j=0;j<8;j++)c=c&1?0xedb88320^(c>>>1):c>>>1;crcTable[i]=c>>>0;}
function crc32(buf,from,to) {let crc=0xffffffff;for(let i=from;i<to;i++)crc=crcTable[(crc^buf[i])&255]^(crc>>>8);return (crc^0xffffffff)>>>0;}
export function pngSize(buf) {
  if(!Buffer.isBuffer(buf)||buf.length<57||!buf.subarray(0,8).equals(SIGNATURE))fail('png_file is not a valid PNG signature');
  let offset=8,seenIHDR=false,seenIDAT=false,seenIEND=false,width,height,bitDepth,color,chunkCount=0;
  const idat=[];
  while(offset<buf.length) {
    if(++chunkCount>10000||offset+12>buf.length) fail('Truncated or excessive PNG chunks');
    const size=buf.readUInt32BE(offset), end=offset+12+size;
    if(size>2*1024*1024||end>buf.length) fail('Invalid PNG chunk size');
    const type=buf.toString('ascii',offset+4,offset+8);
    if(!/^[A-Za-z]{4}$/.test(type))fail('Invalid PNG chunk type');
    if(crc32(buf,offset+4,offset+8+size)!==buf.readUInt32BE(offset+8+size))fail('PNG chunk CRC mismatch');
    if(!seenIHDR){
      if(type!=='IHDR'||size!==13)fail('PNG must begin with a 13-byte IHDR');
      seenIHDR=true;width=buf.readUInt32BE(offset+8);height=buf.readUInt32BE(offset+12);
      if(width<1||height<1||width>2048||height>2048)fail('PNG dimensions must be 1..2048');
      bitDepth=buf[offset+16];color=buf[offset+17];
      if(![0,2,3,4,6].includes(color)||!({0:[1,2,4,8,16],2:[8,16],3:[1,2,4,8],4:[8,16],6:[8,16]}[color].includes(bitDepth))) fail('Unsupported PNG bit depth/color type');
      if(buf[offset+18]!==0||buf[offset+19]!==0||buf[offset+20]!==0)fail('Only PNG compression/filter method 0 and noninterlaced images supported');
    } else if(type==='IHDR')fail('Duplicate IHDR');
    if(type==='IDAT'){seenIDAT=true;idat.push(buf.subarray(offset+8,offset+8+size));}
    if(type==='IEND') {if(size!==0||end!==buf.length)fail('Malformed PNG IEND or trailing data');seenIEND=true;break;}
    offset=end;
  }
  if(!seenIHDR||!seenIDAT||!seenIEND)fail('PNG missing IHDR, IDAT, or IEND');
  const channels={0:1,2:3,3:1,4:2,6:4}[color];
  const row=Math.ceil(width*channels*bitDepth/8),expected=(row+1)*height;
  if(expected>20*1024*1024)fail('PNG decoded image is too large');
  let pixelData;
  try {pixelData=inflateSync(Buffer.concat(idat),{maxOutputLength:expected+1});}
  catch {fail('PNG IDAT cannot be decoded within safe size limits');}
  if(pixelData.length!==expected)fail('PNG decoded image length does not match IHDR dimensions');
  for(let offset=0;offset<expected;offset+=row+1)if(pixelData[offset]>4)fail('Invalid PNG row filter');
  return {width,height};
}
export function embedTexture(model,buf,pngName) {
  const dims=pngSize(buf);
  const scale=dims.width/model.resolution.width;
  if(!Number.isInteger(scale)||scale<1||scale>8||dims.height!==model.resolution.height*scale)fail(`PNG dimensions ${dims.width}x${dims.height} must equal the model resolution ${model.resolution.width}x${model.resolution.height} or a uniform integer multiple of it (2x, 4x: a hi-res skin over the same UV layout)`);
  const uuid=model.textures?.[0]?.uuid || randomUUID();
  model.textures=[{name:pngName,folder:'',namespace:'',id:'0',uuid,source:'data:image/png;base64,'+buf.toString('base64'),mode:'bitmap',saved:false,width:dims.width,height:dims.height,uv_width:model.resolution.width,uv_height:model.resolution.height}];
  for(const element of model.elements)for(const face of Object.values(element.faces||{}))if(element.box_uv===true||face.texture!==null)face.texture=uuid;
  return {texture_uuid:uuid,name:pngName,width:dims.width,height:dims.height,scale,size:buf.length};
}
