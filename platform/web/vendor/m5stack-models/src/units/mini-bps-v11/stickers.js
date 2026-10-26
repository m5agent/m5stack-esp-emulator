import {printedArtwork} from '../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href,back=new URL('./reference-redraw-back.png',import.meta.url).href;
/** Final ordinary PNGs code-redrawn from exact U090-B photographs, without photo crops. */
export function addStickers(host){const films=host.miniBPSV11Assembly.films;return[
 ...(printedArtwork(host,{target:films.front,url:front,size:[5.8,5.8],position:[0,0,4.04],face:'front',depth:.06,name:'Mini BPS v1.1 round front BPS reference redraw',artworkKind:'reference-redraw'})??[]),
 ...(printedArtwork(host,{target:films.back,url:back,size:[16,4],position:[0,7,-3.835],face:'back',depth:.06,name:'Mini BPS v1.1 rear PORT.A pin-label reference redraw',artworkKind:'reference-redraw'})??[])
 ];}
