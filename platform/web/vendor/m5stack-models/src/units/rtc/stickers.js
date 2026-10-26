import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./reference-back.png',import.meta.url).href;
const front=new URL('./reference-front.png',import.meta.url).href;
/** Reference redraws from exact-product official photos; no photo pixels or private vectors. */
export function addStickers(host){
 const panels=[];
 panels.push(...(printedArtwork(host,{target:host.parts['RTC complete native double shell'],url:back,size:[16, 28],position:[0, 7.2, -3.8],face:'back',depth:.14,name:'rtc reference-redrawn back label',artworkKind:'reference-redraw'})??[]));
 panels.push(...(printedArtwork(host,{target:host.parts['RTC complete native double shell'],url:front,size:[16, 28],position:[0, 7.2, 3.8],face:'front',depth:.14,name:'rtc reference-redrawn front label',artworkKind:'reference-redraw'})??[]));
 return panels;
}
