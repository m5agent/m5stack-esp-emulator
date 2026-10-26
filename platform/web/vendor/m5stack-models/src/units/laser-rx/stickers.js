import {printedArtwork} from '../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href;
const back=new URL('./reference-redraw-back.png',import.meta.url).href;
/** Code-drawn exact U065 reference labels; no source vector or photograph pixels. */
export function addStickers(host){
 const target=host.parts['Laser RX complete native assembled shell'];
 return [
  ...(printedArtwork(host,{target,url:front,size:[20,14],position:[0,7,3.8],face:'front',depth:.14,name:'Laser RX reference-redrawn receiver and LASER BEAM front label',artworkKind:'reference-redraw'})??[]),
  ...(printedArtwork(host,{target,url:back,size:[16.2,12.2],position:[0,7,-3.8],face:'back',depth:.14,name:'Laser RX reference-redrawn frequency and PORT B back label',artworkKind:'reference-redraw'})??[])
 ];
}
