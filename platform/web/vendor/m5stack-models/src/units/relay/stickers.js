import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){
 return printedArtwork(host,{target:host.parts.housing,url:back,size:[16,28],position:[0,7,-3.8],face:'back',depth:.12,artworkKind:'reference-redraw',name:'Relay rear sticker (reference redraw)'});
}
