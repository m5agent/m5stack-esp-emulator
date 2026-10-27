import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
const rasters={front:new URL('./official-front.png',import.meta.url).href,top:new URL('./official-top.png',import.meta.url).href,back:new URL('./official-back.png',import.meta.url).href,pinout:new URL('./official-pinout.png',import.meta.url).href};
/** Approved final rasters only. Original design and conversion intermediates remain private. */
export function addStickers(host,{native,radio}){
 const front=native['CamS3-5MP complete native front carrier'],back=native['CamS3-5MP complete native back shell'],panels=[];
 panels.push(...(printedArtwork(host,{target:front,url:rasters.front,size:[16,5],position:[0,17.48,2.5],face:'front',depth:.24,name:'CamS3-5MP original-design 5MP front label'})??[]));
 panels.push(...(printedArtwork(host,{target:[front,back],url:rasters.top,size:[16,7.5],position:[0,20.02,-1.4],face:'top',depth:.3,name:'CamS3-5MP original-design top wrap'})??[]));
 panels.push(...(printedArtwork(host,{target:[back,radio.shield],url:rasters.back,size:[16,9.5],position:[0,15.2,-5.3],face:'back',depth:.45,name:'CamS3-5MP original-design rear brand label'})??[]));
 const pinout=printedFilm(host,{url:rasters.pinout,size:[12.8,10.8],position:[0,-12.9,-5.40],face:'back',name:'CamS3-5MP original-design die-cut pinout film'});if(pinout)panels.push(pinout);
 return panels;
}
