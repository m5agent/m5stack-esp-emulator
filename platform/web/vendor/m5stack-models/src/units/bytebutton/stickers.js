import {printedArtwork} from '../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href;
const back=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){
 // All printed graphics belong to fixed native shell faces. The channel caps,
 // toggle levers, lightpipes, native mounting bores and Grove mouths stay free.
 const a=printedArtwork(host,{target:host.parts['ByteButton native front shell'],url:front,size:[53.2,6.6],position:[-7.05,0,5.85],rotation:-Math.PI/2,face:'front',depth:.08,artworkKind:'reference-redraw',name:'ByteButton front channel/title label (reference redraw)'});
 const b=printedArtwork(host,{target:host.parts['ByteButton native rear shell'],url:back,size:[20.8,54],position:[0,0,-5.85],face:'back',depth:.08,artworkKind:'reference-redraw',name:'ByteButton rear pinout/diagram sticker (reference redraw)'});
 return {front:a,back:b};
}
