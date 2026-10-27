import {printedArtwork} from '../../modeling/artwork.js';
const rear=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host,nativeRear){
 return printedArtwork(host,{target:nativeRear,url:rear,size:[19.1,14.2],position:[0,7.1,-3.97],face:'back',depth:.22,artworkKind:'reference-redraw',name:'Step16 rear exact-U198 official-photo diagram redraw'});
}
