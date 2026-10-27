import {printedArtwork} from '../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href,back=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){return[
 ...(printedArtwork(host,{target:host.extEncoderAssembly.encoder.roof,url:front,size:[13.7,9.3],position:[0,10.9,6.7],depth:.12,artworkKind:'reference-redraw',name:'ExtEncoder own-photo connector label reference redraw'})??[]),
 ...(printedArtwork(host,{target:host.parts['ExtEncoder complete native assembled shell'],url:back,size:[16,12.4],position:[0,7.5,-3.8],face:'back',depth:.12,artworkKind:'reference-redraw',name:'ExtEncoder own-photo rear label reference redraw'})??[])
 ];}
