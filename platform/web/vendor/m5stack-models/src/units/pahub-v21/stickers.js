import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./official-back.png',import.meta.url).href;
const chip=new URL('./official-chip.png',import.meta.url).href;
/** Approved final original-design rasters; private vectors and conversion files excluded. */
export function addStickers(host){
 const panels=[];
 panels.push(...(printedArtwork(host,{target:host.parts['PaHUB v2.1 assembled shell'],url:back,size:[16,28],position:[0,7,-3.8],face:'back',depth:.12,name:'PaHUB v2.1 original-design rear label'})??[]));
 panels.push(...(printedArtwork(host,{target:host.body.getObjectByName('PaHUB PCA9548AP physical package'),url:chip,size:[3.4,7],position:[0,4.3,2.15],face:'front',depth:.14,name:'PaHUB v2.1 original-design chip address-reference label'})??[]));
 return panels;
}
