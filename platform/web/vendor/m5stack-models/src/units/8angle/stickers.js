import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
const back=new URL('./official-back.png',import.meta.url).href;
const front=new URL('./reference-front.png',import.meta.url).href;
export function addStickers(host){
 if(host.options.artwork===false)return;
 printedFilm(host,{url:back,size:[20,30],position:[0,-31,-4.81],face:'back',parent:host.parts['8Angle back shell'],name:'8Angle original rear label bridging service opening'});
 printedArtwork(host,{target:host.parts['8Angle front shell'],url:front,size:[24,128],position:[0,0,5],depth:1,face:'front',artworkKind:'reference-redraw',name:'8Angle CH1-CH8 and switch markings from official photos'});
}
