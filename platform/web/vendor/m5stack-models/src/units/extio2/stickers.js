import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./reference-redraw-back.png',import.meta.url).href;
/** Exact U011-B rear label redrawn from official photo, never a photograph crop. */
export function addStickers(host){
 return printedArtwork(host,{target:host.parts['EXT.IO2 complete native assembled shell'],url:back,size:[16.3,12.2],position:[0,7,-4.9],face:'back',depth:.16,name:'EXT.IO2 reference-redrawn rear pin legend',artworkKind:'reference-redraw'})??[];
}
