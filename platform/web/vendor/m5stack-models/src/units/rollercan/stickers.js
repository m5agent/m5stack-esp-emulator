import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
const portA=new URL('./reference-redraw-port-a.png',import.meta.url).href,pwrcan=new URL('./reference-redraw-pwrcan.png',import.meta.url).href,debug=new URL('./reference-redraw-debug.png',import.meta.url).href;
export function addStickers(host){
 const target=host.parts['RollerCAN native fixed OLED face shell'],panels=[];
 panels.push(...(printedArtwork(host,{target,url:portA,size:[7.2,9.2],position:[0,-19.8,15.9],face:'bottom',rotation:Math.PI/2,depth:.14,artworkKind:'reference-redraw',name:'RollerCAN fixed PORT.A label (same-SKU photo redraw)'})??[]));
 // The exact U188 OLED-face photo shows a continuous PWRCAN adhesive film
 // across the native service openings; fixed socket hardware remains behind it.
 const film=printedFilm(host,{parent:target,url:pwrcan,size:[16,9.2],position:[14.85,-19.825,0],face:'bottom',rotation:Math.PI/2,artworkKind:'reference-redraw',name:'RollerCAN fixed PWRCAN adhesive film (same-SKU photo redraw)'});if(film)panels.push(film);
 panels.push(...(printedArtwork(host,{target:host.parts['RollerCAN native fixed motor seat shell'],url:debug,size:[16,5.8],position:[0,-13.35,-19.8],face:'back',depth:.3,artworkKind:'reference-redraw',name:'RollerCAN fixed debug-port label (same-SKU photo redraw)'})??[]));return panels;
}
