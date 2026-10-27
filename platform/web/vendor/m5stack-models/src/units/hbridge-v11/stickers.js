import{printedArtwork,printedFilm}from'../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href,back=new URL('./reference-redraw-back.png',import.meta.url).href;
/** Own label text/geometry newly redrawn to final ordinary PNG; no photo texture. */
export function addStickers(host){
 const shell=host.parts['HBridge v1.1 native front shell'];
 return[printedFilm(host,{parent:shell,url:front,size:[16,26.4],position:[0,1.95,3.81],artworkKind:'reference-redraw',name:'HBridge v1.1 real front adhesive film bridging native narrow recess'}),...(printedArtwork(host,{target:host.parts['HBridge v1.1 native rear shell'],url:back,size:[16,35.2],position:[0,6.25,-3.8],face:'back',depth:.13,artworkKind:'reference-redraw',name:'HBridge v1.1 rear INA199 own diagram reference redraw'})??[])].filter(Boolean);
}
