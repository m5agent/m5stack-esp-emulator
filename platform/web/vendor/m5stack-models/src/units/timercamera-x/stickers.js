import{printedArtwork}from'../../modeling/artwork.js';import{spec}from'./dimensions.js';
const back=new URL('./artwork/back.png',import.meta.url).href;
export function addStickers(host){return printedArtwork(host,{target:host.timerCameraXAssembly.film,url:back,size:spec.label.size,position:spec.label.position,face:'back',depth:.12,name:'TimerCamera-X own rear manufacturer label accurate photo-reference redraw',artworkKind:'reference-redraw'})??[];}
