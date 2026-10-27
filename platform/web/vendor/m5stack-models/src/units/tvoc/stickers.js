import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./reference-redraw-back.png',import.meta.url).href;
const front=new URL('./reference-redraw-front.png',import.meta.url).href;
export function addStickers(host){
 const panels=printedArtwork(host,{target:host.parts.housing,url:back,size:[16,4],position:[0,7,-3.8],face:'back',depth:.12,artworkKind:'reference-redraw',name:'Mini TVOC/eCO2 rear sticker (reference redraw)'})??[];
 panels.push(...(printedArtwork(host,{target:host.parts.housing,url:front,size:[17.8,2.7],position:[0,5.55,3.8],face:'front',depth:.12,artworkKind:'reference-redraw',name:'Mini TVOC/eCO2 front sticker (reference redraw)'})??[]));
 return panels;
}
