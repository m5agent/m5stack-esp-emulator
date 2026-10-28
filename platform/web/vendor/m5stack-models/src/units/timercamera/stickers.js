/** MIT code; ordinary own-photo PCB silkscreen redraw,no film or photo crop. */
import{printedArtwork}from'../../modeling/artwork.js';const front=new URL('./reference-redraw-front.png',import.meta.url).href;
export function addStickers(host,pcb){return printedArtwork(host,{target:pcb,url:front,size:[20,45],position:[0,0,.605],face:'front',depth:.07,artworkKind:'reference-redraw',name:'Bare U082 own legible PCB silkscreen'})??[];}
