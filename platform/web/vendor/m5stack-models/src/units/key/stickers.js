import {printedFilm} from '../../modeling/artwork.js';

const rear=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){
 return printedFilm(host,{url:rear,size:[17.7,18.1682539683],position:[0,7.275,-3.825],face:'back',parent:host.parts['Key back shell'],artworkKind:'reference-redraw',name:'Key rear adhesive label (reference redraw)'});
}
