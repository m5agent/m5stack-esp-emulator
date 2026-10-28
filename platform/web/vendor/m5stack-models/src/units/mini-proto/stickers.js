import {printedArtwork} from '../../modeling/artwork.js';
import {spec} from './dimensions.js';
const back=new URL('./artwork/back.png',import.meta.url).href;
export function addStickers(host){
 if(!host.miniProtoAssembly.film)return [];
 return printedArtwork(host,{target:host.miniProtoAssembly.film,url:back,size:spec.labels.back.size,position:spec.labels.back.position,face:'back',depth:.12,name:'Mini Proto exact U064 official-photo rear label code redraw',artworkKind:'reference-redraw'})??[];
}
