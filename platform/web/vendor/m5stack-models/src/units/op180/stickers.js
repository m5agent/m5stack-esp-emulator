import{printedArtwork}from'../../modeling/artwork.js';const back=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){return printedArtwork(host,{target:host.op180Assembly.labels.back,url:back,size:[16,12],position:[0,5,-3.85],face:'back',depth:.13,name:'OP180 rear exact-model reference redraw',artworkKind:'reference-redraw'})??[];}
