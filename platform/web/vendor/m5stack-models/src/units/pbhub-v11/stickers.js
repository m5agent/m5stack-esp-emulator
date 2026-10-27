import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./official-back.png',import.meta.url).href;
/** Exact U041-B content is Pb.HUB / STM32 F030 / V1.1; private vectors excluded. */
export function addStickers(host){
 return printedArtwork(host,{target:host.parts['PbHUB v1.1 assembled front and rear shell'],url:back,size:[16,28],position:[0,7,-3.8],face:'back',depth:.12,name:'PbHUB v1.1 original-design rear label'})??[];
}
