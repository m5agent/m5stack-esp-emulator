import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
const portA=new URL('./reference-redraw-port-a.png',import.meta.url).href,pwrcan=new URL('./reference-redraw-pwrcan.png',import.meta.url).href,debug=new URL('./reference-redraw-debug.png',import.meta.url).href;
export function addStickers(host){
 const target=host.parts['RollerCAN-Lite native fixed OLED face shell'],panels=[];
 panels.push(...(printedArtwork(host,{target,url:portA,size:[7.2,9.2],position:[0,-19.8,15.9],face:'bottom',rotation:Math.PI/2,depth:.14,artworkKind:'reference-redraw',name:'RollerCAN-Lite fixed PORT.A label (own Lite photo redraw)'})??[]));
 // The own U188-Lite OLED-face photo shows the continuous PWRCAN film. It
 // remains fixed and does not acquire the standard model's rotating top parts.
 const film=printedFilm(host,{parent:target,url:pwrcan,size:[16,9.2],position:[14.85,-19.825,0],face:'bottom',rotation:Math.PI/2,artworkKind:'reference-redraw',name:'RollerCAN-Lite fixed PWRCAN adhesive film (own Lite photo redraw)'});if(film)panels.push(film);
 panels.push(...(printedArtwork(host,{target:host.parts['RollerCAN-Lite native fixed motor seat shell'],url:debug,size:[16,5.8],position:[0,-13.35,-19.8],face:'back',depth:.3,artworkKind:'reference-redraw',name:'RollerCAN-Lite fixed debug-port label (own Lite photo redraw)'})??[]));return panels;
}
