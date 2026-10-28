import {printedArtwork} from '../../modeling/artwork.js';
import {spec} from './dimensions.js';
const front=new URL('./artwork/front.png',import.meta.url).href;
const back=new URL('./artwork/back.png',import.meta.url).href;
export function addStickers(host){const a=host.eightServosChainAssembly;return [['front',front,a.labels.front],['back',back,a.labels.back]].flatMap(([face,url,target])=>printedArtwork(host,{target,url,...spec.labels[face],face,depth:.12,artworkKind:'official-vector-raster',name:'U223 own '+face+' source artwork on independent actual adhesive carrier'})??[]);}
