import{printedArtwork}from'../../modeling/artwork.js';const back=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){return printedArtwork(host,{target:host.fingerAssembly.labels.back,url:back,size:[16,28],position:[0,7.2,-3.84],face:'back',depth:.12,name:'Finger rear FPC1020A exact-model reference redraw',artworkKind:'reference-redraw'})??[];}
