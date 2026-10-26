import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./reference-back.png',import.meta.url).href;
/** Reference redraws from exact-product official photos; no photo pixels or private vectors. */
export function addStickers(host){
 const panels=[];
 panels.push(...(printedArtwork(host,{target:host.parts['ToF4M native assembled front and rear shells'],url:back,size:[16, 12],position:[0, 7, -3.8],face:'back',depth:.14,name:'tof4m reference-redrawn back label',artworkKind:'reference-redraw'})??[]));
 return panels;
}
