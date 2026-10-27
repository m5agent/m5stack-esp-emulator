import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
const front=new URL('./official-front.png',import.meta.url).href;
const back=new URL('./official-back.png',import.meta.url).href;
const certification=new URL('./official-certification.png',import.meta.url).href;
export function addStickers(host){
 const panels=[];
 panels.push(...(printedArtwork(host,{target:host.parts['PoESP32 complete native front shell'],url:front,size:[18.5,51],position:[0,7,9.4],face:'front',depth:.16,name:'PoESP32 official front flat artwork'})??[]));
 // Exact U138 photographs show the continuous rear film crossing the original
 // open RJ45-roof relief. The real shield and insertion body remain behind it.
 const film=printedFilm(host,{parent:host.parts['PoESP32 complete native rear shell'],url:back,size:[16.2,45],position:[0,3.7,-9.408],face:'back',name:'PoESP32 official continuous rear adhesive film'});if(film)panels.push(film);
 // Certification position is a visual registration estimate: the exact flat
 // design is supplied, but the available assembled photos do not expose it.
 panels.push(...(printedArtwork(host,{target:host.parts['PoESP32 complete native rear shell'],url:certification,size:[22,7.392],position:[11.84,0,-2],face:'right',rotation:Math.PI/2,depth:.55,name:'PoESP32 official certification flat artwork (position inferred)'})??[]));
 return panels;
}
