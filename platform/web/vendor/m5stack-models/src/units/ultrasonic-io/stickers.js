import {printedArtwork} from '../../modeling/artwork.js';
import {spec} from './dimensions.js';
const back=new URL('./artwork/back.png',import.meta.url).href;
export function addStickers(host){if(!host.ultrasonicIOAssembly.film)return[];const s=spec.labels.back;return printedArtwork(host,{target:host.ultrasonicIOAssembly.film,url:back,size:s.size,position:s.position,face:'back',depth:.12,name:'Ultrasonic-IO exact U098-B2 original rear body label raster',artworkKind:'source-vector-raster'})??[];}
