import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href;
const back=new URL('./reference-redraw-back.png',import.meta.url).href;
const end=new URL('./reference-redraw-end.png',import.meta.url).href;
export function addStickers(host){
 const platform=host.parts['Mini Scales native weighing platform'];
 // Exact U177 label is continuous over its native platform service openings.
 // The rear T-shaped continuous adhesive also spans its short neck recess.
 // Alpha follows the actual die-cut outline; all original geometry remains.
 return [printedFilm(host,{url:front,size:[10.2,18.2],position:[0,-3.6,8.812],face:'front',parent:platform,artworkKind:'reference-redraw',name:'Mini Scales platform MAX5KG label (reference redraw)'}),printedFilm(host,{parent:host.parts['Mini Scales native lower housing'],url:back,size:[21.2,29.5],position:[0,1.75,-8.812],face:'back',artworkKind:'reference-redraw',name:'Mini Scales rear schematic label (reference redraw)'}),printedArtwork(host,{target:platform,url:end,size:[6.2,3.2],position:[0,-19.72,5.6],face:'bottom',depth:.5,artworkKind:'reference-redraw',name:'Mini Scales Grove-end arrow label (reference redraw)'})];
}
