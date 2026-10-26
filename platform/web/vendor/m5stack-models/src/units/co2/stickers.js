import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./reference-back.png',import.meta.url).href;
/** Reference redraws from exact-product official photos; no photo pixels or private vectors. */
export function addStickers(host){
 const panels=[];
 panels.push(...(printedArtwork(host,{target:host.parts['CO2 native assembled double shell'],url:back,size:[16, 28],position:[0, 7.2, -7.8],face:'back',depth:.14,name:'co2 reference-redrawn back label',artworkKind:'reference-redraw'})??[]));
 return panels;
}
