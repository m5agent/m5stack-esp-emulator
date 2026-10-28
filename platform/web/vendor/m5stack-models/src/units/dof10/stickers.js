import {printedArtwork} from '../../modeling/artwork.js';
import {spec} from './dimensions.js';
const images={front:new URL('./source-vector-front.png',import.meta.url).href,axis:new URL('./source-vector-axis.png',import.meta.url).href,back:new URL('./source-vector-back.png',import.meta.url).href};
export function addStickers(host){const out=[];for(const face of['front','axis','back'])out.push(...(printedArtwork(host,{target:host.dof10Assembly.labels[face],url:images[face],size:spec.labels[face].size,position:spec.labels[face].position,face:face==='back'?'back':'front',depth:.12,name:'DoF10 exact U230 original '+face+' body label',artworkKind:'source-vector-raster'})??[]));return out;}
