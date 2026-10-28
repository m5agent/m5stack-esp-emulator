import {printedArtwork} from '../../modeling/artwork.js';
import {spec} from './dimensions.js';
const back=new URL('./artwork/back.png',import.meta.url).href;
export function addStickers(host){return printedArtwork(host,{target:host.unitVOv7740Assembly.label,url:back,size:spec.label.size,position:spec.label.position,face:'back',depth:.12,name:'UnitV-OV7740 exact official flat rear artwork',artworkKind:'official-flat-raster'})??[];}
