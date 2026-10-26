import {printedArtwork} from '../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href;
const back=new URL('./reference-redraw-back.png',import.meta.url).href;
/** Exact U084 photo-derived text and illustration, code drawn without photographic pixels. */
export function addStickers(host){
 const target=host.parts['Hall complete native assembled shell'];
 return [
  ...(printedArtwork(host,{target,url:front,size:[20,14],position:[0,7,3.8],face:'front',depth:.14,name:'Hall reference-redrawn directional diagram and product label',artworkKind:'reference-redraw'})??[]),
  ...(printedArtwork(host,{target,url:back,size:[16.2,12.2],position:[0,7,-3.8],face:'back',depth:.14,name:'Hall reference-redrawn A3144E SIGNAL and pinout label',artworkKind:'reference-redraw'})??[])
 ];
}
