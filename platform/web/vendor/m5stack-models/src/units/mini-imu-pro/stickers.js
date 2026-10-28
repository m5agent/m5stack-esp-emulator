import {printedArtwork} from '../../modeling/artwork.js';
import {spec} from './dimensions.js';
const front=new URL('./artwork/front.png',import.meta.url).href;
const axis=new URL('./artwork/axis.png',import.meta.url).href;
const back=new URL('./artwork/back.png',import.meta.url).href;
export function addStickers(host){const f=host.miniIMUProAssembly.films,out=[];for(const[face,url]of[['front',front],['axis',axis],['back',back]]){const cfg=spec.labels[face];out.push(...(printedArtwork(host,{target:f[face],url,size:cfg.size,position:cfg.position,face:face==='back'?'back':'front',depth:.1,name:'Mini IMU-Pro own official-photo '+face+' accurate code redraw',artworkKind:'reference-redraw'})??[]));}return out;}
