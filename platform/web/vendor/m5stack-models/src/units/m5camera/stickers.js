/** MIT code; ordinary exact-own rear label redraw,not photo pixels. */
import{printedArtwork}from'../../modeling/artwork.js';const rear=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host,film){return printedArtwork(host,{target:film,url:rear,size:[21,38],position:[0,3,-4.005],face:'back',depth:.08,artworkKind:'reference-redraw',name:'Original U017 own readable rear label'})??[];}
