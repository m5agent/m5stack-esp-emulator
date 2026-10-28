/** MIT code; own exact-model legible PCB silk redrawn as ordinaryPNG. */
import{printedArtwork}from'../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href,back=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host,pcb){return[...(printedArtwork(host,{target:pcb,url:front,size:[57,21],position:[0,0,1],depth:.08,artworkKind:'reference-redraw',name:'M5Bit own fifteen IO numbers andDA CL V G PCB silk'})??[]),...(printedArtwork(host,{target:pcb,url:back,size:[57,21],position:[0,0,0],face:'back',depth:.08,artworkKind:'reference-redraw',name:'M5Bit ownM5:bit CLASSROOM LM2 PCB silk'})??[])];}
