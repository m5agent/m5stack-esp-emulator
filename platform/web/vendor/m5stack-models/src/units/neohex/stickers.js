import{printedArtwork}from'../../modeling/artwork.js';
const front=new URL('./artwork/front.png',import.meta.url).href;
const back=new URL('./artwork/back.png',import.meta.url).href;
export function addStickers(host){return[['front',front,.5],['back',back,-.5]].flatMap(([face,url,z])=>printedArtwork(host,{target:host.neohexAssembly.board.pcb,url,size:[40,40],position:[0,0,z],face,depth:.12,artworkKind:'reference-redraw',name:'NeoHEX exact own fixed PCB '+face+' silkscreen;no adhesive film'})??[]);}
