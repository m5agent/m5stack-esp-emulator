import {printedArtwork} from '../../modeling/artwork.js';
const first=new URL('./official-relay-1.png',import.meta.url).href;
const second=new URL('./official-relay-2.png',import.meta.url).href;
const back=new URL('./official-back.png',import.meta.url).href;
export function addStickers(host,{relays}){
 const panels=[];
 for(const[i,url]of[first,second].entries()){
  const target=relays[i];
  panels.push(...(printedArtwork(host,{target,url,size:[18,9.8],position:[target.position.x,target.position.y,15],depth:.14,name:`2Relay channel ${i+1} official sealed-package label`})??[]));
 }
 panels.push(...(printedArtwork(host,{target:host.parts['2Relay native rear shell'],url:back,size:[16,37],position:[0,7.4,-3.8],face:'back',depth:.15,name:'2Relay official rear specification label'})??[]));
 return panels;
}
