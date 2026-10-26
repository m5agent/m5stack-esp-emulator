import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./redrawn-back.png',import.meta.url).href;
export function addStickers(host){
 return printedArtwork(host,{target:host.parts['Limit back shell'],url:back,size:[18, 11.936842105263159],position:[0, 7.5, -4.55],face:'back',depth:.12,artworkKind:'reference-redraw',name:'limit rear label - official-photo reference redraw'});
}
