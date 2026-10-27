import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./reference-back.png',import.meta.url).href;
/** Reference redraws from exact-product official photos; no photo pixels or private vectors. */
export function addStickers(host){
 const panels=[];
 panels.push(...(printedArtwork(host,{target:host.parts['OLED native rear shell'],url:back,size:[20, 38],position:[0, 7, -3.8],face:'back',depth:.14,name:'oled reference-redrawn back label',artworkKind:'reference-redraw'})??[]));
 return panels;
}
