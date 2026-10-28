import{printedArtwork}from'../../modeling/artwork.js';
const front=new URL('./artwork/front.png',import.meta.url).href;
const back=new URL('./artwork/back.png',import.meta.url).href;
export function addStickers(host){return[['front',front,.5],['back',back,-.5]].flatMap(([face,url,z])=>printedArtwork(host,{target:host.necoAssembly.board.pcb,url,size:[47.1,44.6],position:[0,0,z],face,depth:.12,artworkKind:'reference-redraw',name:'Neco own readable '+face+' PCB silkscreen; no adhesive film'})??[]);}
