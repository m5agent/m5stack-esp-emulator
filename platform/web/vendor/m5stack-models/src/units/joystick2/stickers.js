import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
const back=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){
 // Continuous adhesive label visible on exact U024-V2 rear photos spans
 // native rear service openings; no cap, gimbal, Grove or lightpipe is printed.
 return printedFilm(host,{url:back,size:[19.4,21.6],position:[0,7.4,-3.812],face:'back',parent:host.parts['Joystick2 native rear shell'],artworkKind:'reference-redraw',name:'Joystick2 rear Hall/button diagram (reference redraw)'});
}
