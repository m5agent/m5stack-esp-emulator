import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./redrawn-back.png',import.meta.url).href;
export function addStickers(host){
 return printedArtwork(host,{target:host.parts.housing,url:back,size:[15.774193548387096, 12],position:[0, 7, -3.8],face:'back',depth:.12,artworkKind:'reference-redraw',name:'button rear label - official-photo reference redraw'});
}
