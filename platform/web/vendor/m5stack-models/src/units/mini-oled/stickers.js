import{printedArtwork}from'../../modeling/artwork.js';
const front=new URL('./artwork/front.png',import.meta.url).href;
const back=new URL('./artwork/back.png',import.meta.url).href;
/** Readable exact-U166 bare-PCB silkscreen, code redrawn from own official photos. */
export function addStickers(host){const target=host.miniOledAssembly.board.pcb,panels=[];for(const[face,url,z]of[['front',front,-2.2],['back',back,-3.2]])panels.push(...(printedArtwork(host,{target,url,size:[25.8,12],position:[0,0,z],face,depth:.08,name:'Mini OLED own '+face+' PCB silkscreen',artworkKind:'reference-redraw'})??[]));return panels;}
