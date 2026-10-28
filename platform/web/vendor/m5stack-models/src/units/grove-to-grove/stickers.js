import {printedArtwork} from '../../modeling/artwork.js';
import {spec} from './dimensions.js';
const images={front:new URL('./reference-redraw-front.png',import.meta.url).href,back:new URL('./reference-redraw-back.png',import.meta.url).href};
export function addStickers(host){const panels=[];for(const face of['front','back'])panels.push(...(printedArtwork(host,{target:host.groveToGroveAssembly.films[face],url:images[face],size:spec.labels[face].size,position:spec.labels[face].position,face,depth:.12,name:'Grove2Grove exact U148 official-reference redraw '+face+' label',artworkKind:'reference-redraw'})??[]));return panels;}
