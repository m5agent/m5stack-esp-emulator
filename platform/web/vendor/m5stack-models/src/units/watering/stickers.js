import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./source-vector-back.png',import.meta.url).href,motor=new URL('./reference-redraw-motor.png',import.meta.url).href;
export function addStickers(host,assembly){return[
 ...(printedArtwork(host,{target:assembly.native['Watering complete native assembled shell and pump saddle'],url:back,size:[16,20],position:[0,-21,-3.8],face:'back',depth:.2,name:'Watering exact source contour rear label with preview-guided fill recovery',artworkKind:'source-vector-raster'})??[]),
 ...(printedArtwork(host,{target:assembly.pump.motor,url:motor,size:[18,16],position:[0,-22.5,27.3],face:'front',depth:4.4,name:'Watering motor can model mark reference redraw',artworkKind:'reference-redraw'})??[])
];}
