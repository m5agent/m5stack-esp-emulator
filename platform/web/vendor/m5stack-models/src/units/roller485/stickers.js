import {printedArtwork,printedFilm} from '../../modeling/artwork.js';

const portA=new URL('./reference-redraw-port-a.png',import.meta.url).href;
const pwr485=new URL('./reference-redraw-pwr485.png',import.meta.url).href;
export function addStickers(host){
 const target=host.parts['Roller485 native fixed OLED face shell'],panels=[];
 const add=(options)=>panels.push(...(printedArtwork(host,{target,face:'bottom',rotation:Math.PI/2,depth:.12,artworkKind:'reference-redraw',...options})??[]));
 add({url:portA,size:[7.2,9.2],position:[0,-19.8,15.9],name:'Roller485 fixed PORT.A label (reference redraw)'});
 // The real continuous PWR485 film bridges the two native service apertures.
 const film=printedFilm(host,{parent:target,url:pwr485,size:[16,9.2],position:[14.85,-19.825,0],face:'bottom',rotation:Math.PI/2,artworkKind:'reference-redraw',name:'Roller485 fixed PWR485 label (reference redraw)'});if(film)panels.push(film);
 return panels;
}
