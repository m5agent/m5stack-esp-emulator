import{printedArtwork}from'../../modeling/artwork.js';
const front=new URL('./artwork/front.png',import.meta.url).href;
const back=new URL('./artwork/back.png',import.meta.url).href;
export function addStickers(host){const a=host.glassAssembly;return[...(printedArtwork(host,{target:a.board.pcb,url:front,size:[42,53],position:[0,0,2.8],face:'front',depth:.12,artworkKind:'reference-redraw',name:'Glass own readable GLASS/M5STACK front PCB silkscreen; no film'})??[]),...(printedArtwork(host,{target:a.cover.plate,url:back,size:[42,21],position:[0,-9,-2.65],face:'back',depth:.12,artworkKind:'reference-redraw',name:'Glass own readable M5STACK/A/B/GVDC rear cover print; no film'})??[])];}
