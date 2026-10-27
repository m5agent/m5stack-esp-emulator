import {printedArtwork} from '../../modeling/artwork.js';
const front=new URL('./official-front.png',import.meta.url).href;
const back=new URL('./official-back.png',import.meta.url).href;
export function addStickers(host){
 const panels=[];
 panels.push(...(printedArtwork(host,{target:host.body.getObjectByName('RFID dielectric front cover'),url:front,size:[17.8,27.8],position:[0,6.1,3.94],face:'front',depth:.12,name:'RFID2 official antenna face sticker'})??[]));
 panels.push(...(printedArtwork(host,{target:host.parts['rear-shell'],url:back,size:[16,28],position:[0,8,-3.8],face:'back',depth:.12,name:'RFID2 official rear sticker'})??[]));
 return panels;
}
