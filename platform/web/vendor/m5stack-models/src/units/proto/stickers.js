import {printedArtwork} from '../../modeling/artwork.js';
import {spec} from './dimensions.js';
const image=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){if(!host.protoAssembly.film)return[];return printedArtwork(host,{target:host.protoAssembly.film,url:image,size:spec.labels.back.size,position:spec.labels.back.position,face:'back',depth:.12,name:'Proto exact U022 official-reference rear label redraw',artworkKind:'reference-redraw'})??[];}
