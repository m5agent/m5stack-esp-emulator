import {printedArtwork} from '../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href,back=new URL('./reference-redraw-back.png',import.meta.url).href;
/** Only final rasters; code-redrawn from the same-model official photographs. */
export function addStickers(host){const target=host.parts['TMOS PIR complete native assembled front and rear shell'];return[
 ...(printedArtwork(host,{target,url:front,size:[16.4,3.5],position:[0,13.6,4],face:'front',depth:.12,name:'TMOS PIR front model label reference redraw',artworkKind:'reference-redraw'})??[]),
 ...(printedArtwork(host,{target,url:back,size:[16,12],position:[0,7,-3.8],face:'back',depth:.14,name:'TMOS PIR rear sensor and PORT.A pin-label reference redraw',artworkKind:'reference-redraw'})??[])
 ];}
