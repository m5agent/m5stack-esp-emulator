import {printedFilm} from '../../modeling/artwork.js';
const front=new URL('./reference-front.png',import.meta.url).href;
const back=new URL('./reference-back.png',import.meta.url).href;
/** Exact U197 adhesive labels bridge native package recesses, backed by real jack/card solids. */
export function addStickers(host){
 const panels=[];
 const a=printedFilm(host,{url:front,size:[18.4,29.6],position:[0,8,3.94],face:'front',name:'AudioPlayer reference-redrawn front adhesive label',artworkKind:'reference-redraw'});if(a)panels.push(a);
 const b=printedFilm(host,{url:back,size:[20.3,28.4],position:[0,7.2,-4.015],face:'back',name:'AudioPlayer reference-redrawn rear adhesive label',artworkKind:'reference-redraw'});if(b)panels.push(b);
 return panels;
}
