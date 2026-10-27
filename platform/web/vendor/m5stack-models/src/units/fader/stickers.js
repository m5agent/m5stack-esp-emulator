import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
const back=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){
 // Exact U123 photo shows a continuous rear adhesive label over the native
 // service aperture. The original PCB and potentiometer remain behind it.
 return printedFilm(host,{url:back,size:[16.8,44.4],position:[0,7.5,-5.012],face:'back',parent:host.parts['Fader native rear shell'],artworkKind:'reference-redraw',name:'Fader rear adhesive diagram (reference redraw)'});
}
