import {printedFilm} from '../../modeling/artwork.js';

export function addStickers(host){
 // The factory adhesive sheet spans the molded rear mounting recesses. Keep
 // those recesses beneath the real printed film instead of painting their walls.
 printedFilm(host,{parent:host.parts['bottom-cover'],url:new URL('./artwork/rear-main.png',import.meta.url).href,size:[34.7666672,51.1],position:[-7.8,0,-8.275],face:'back',name:'Official Core2 v1.1 circuit adhesive film'});
 // The certification film is on the +Y white edge, offset toward -X. It
 // bridges the native mounting recess beneath it in the assembled product.
 printedFilm(host,{parent:host.parts['upper-housing'],url:new URL('./artwork/certification.png',import.meta.url).href,size:[16.1,12.1333335],position:[-8.2,27.01,0],face:'top',rotation:Math.PI,name:'Official Core2 v1.1 certification adhesive film'});
}
