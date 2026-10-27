import {printedArtwork} from '../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href;
const back=new URL('./official-back.png',import.meta.url).href;
/** Final rasters only. Source vectors and private mappings are not distributed. */
export function addStickers(host){
 const target=host.parts['UHF RFID complete native assembled shell'];
 return[
  ...(printedArtwork(host,{target,url:front,size:[33,22],position:[0,-2,5.75],face:'front',depth:.16,name:'UHF RFID reference-redrawn front antenna and tag mark',artworkKind:'reference-redraw'})??[]),
  ...(printedArtwork(host,{target,url:back,size:[30,30],position:[0,0,-5.55],face:'back',depth:.14,name:'UHF RFID current official rear product and UART label',artworkKind:'official-vector-raster'})??[])
 ];
}
