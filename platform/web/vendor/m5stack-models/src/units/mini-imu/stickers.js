import {printedArtwork} from '../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href;
const back=new URL('./reference-redraw-back.png',import.meta.url).href;
const axes=new URL('./reference-redraw-axes.png',import.meta.url).href;
/** Exact U095 photo-derived text and axis artwork; no photographic pixels. */
export function addStickers(host){
 const target=host.parts['Mini IMU complete native assembled shell'];
 return [
  ...(printedArtwork(host,{target,url:front,size:[18,4],position:[0,7.1,3.8],face:'front',depth:.14,name:'Mini IMU reference-redrawn IMU MPU6886 front label',artworkKind:'reference-redraw'})??[]),
  ...(printedArtwork(host,{target,url:back,size:[16.4,4.5],position:[0,7.1,-3.8],face:'back',depth:.14,name:'Mini IMU reference-redrawn PORT A I2C rear label',artworkKind:'reference-redraw'})??[]),
  ...(printedArtwork(host,{target,url:axes,size:[6,6],position:[0,0,4],face:'front',depth:.14,name:'Mini IMU reference-redrawn XYZ axis label',artworkKind:'reference-redraw'})??[])
 ];
}
