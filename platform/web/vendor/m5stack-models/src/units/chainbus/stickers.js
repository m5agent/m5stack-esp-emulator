import {printedArtwork} from '../../modeling/artwork.js';
import {spec} from './dimensions.js';
const images={front:new URL('./source-vector-front.png',import.meta.url).href,back:new URL('./source-vector-back.png',import.meta.url).href};
export function addStickers(host){
 const panels=[];for(const face of['front','back'])panels.push(...(printedArtwork(host,{target:host.chainbusAssembly.films[face],url:images[face],size:spec.labels[face].size,position:spec.labels[face].position,face,depth:.12,name:'ChainBus exact U212 original '+face+' body label',artworkKind:'source-vector-raster'})??[]));return panels;
}
