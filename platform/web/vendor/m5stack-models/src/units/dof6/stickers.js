import {printedArtwork} from '../../modeling/artwork.js';
import {spec} from './dimensions.js';
const front=new URL('./artwork/front.png',import.meta.url).href;
const axis=new URL('./artwork/axis.png',import.meta.url).href;
const back=new URL('./artwork/back.png',import.meta.url).href;
const images={front,axis,back};
export function addStickers(host){const out=[];for(const face of['front','axis','back'])out.push(...(printedArtwork(host,{target:host.dof6Assembly.labels[face],url:images[face],size:spec.labels[face].size,position:spec.labels[face].position,face:face==='back'?'back':'front',depth:.12,name:'DoF6 exact U228 original '+face+' body label',artworkKind:'source-vector-raster'})??[]));return out;}
