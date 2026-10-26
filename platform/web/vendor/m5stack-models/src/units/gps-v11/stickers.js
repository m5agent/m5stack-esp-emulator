import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href;
const back=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){
 const target=host.parts.housing;
 return [printedArtwork(host,{target,url:front,size:[15.8,27.5],position:[0,7.25,3.8],face:'front',depth:.1,artworkKind:'reference-redraw',name:'GPS v1.1 front label (reference redraw)'}),printedArtwork(host,{target,url:back,size:[15.8,27.5],position:[0,7.25,-3.8],face:'back',depth:.1,artworkKind:'reference-redraw',name:'GPS v1.1 back label (reference redraw)'})];
}
