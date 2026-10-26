import {printedFilm} from '../../modeling/artwork.js';
const back=new URL('./redrawn-back.png',import.meta.url).href;
export function addStickers(host){
 // The exact-model rear photograph shows one continuous adhesive label over
 // the native rear service aperture. It is a physical film, not paint on the
 // inner PCB or an invented replacement shell.
 return printedFilm(host,{parent:host.parts.rear,url:back,size:[16, 13.170731707317072],position:[0, 6.5, -5.81],face:'back',artworkKind:'reference-redraw',name:'encoder rear adhesive film - official-photo reference redraw'});
}
