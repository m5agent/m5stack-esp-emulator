import {printedFilm,printedArtwork} from '../../modeling/artwork.js';

export function addStickers(host){
 for(const panel of printedArtwork(host,{target:host.parts['ext-lid'],url:new URL('./artwork/reference-redraw-ext.png',import.meta.url).href,size:[11.8,38.2],position:[16.7,0,-8.26],face:'back',depth:.12,artworkKind:'reference-redraw',name:'Core2 v1.1 EXT CORE2 nameplate (reference redraw)'})??[])panel.userData.source='reference-redraw';
 // The factory adhesive sheet spans the molded rear mounting recesses. Keep
 // those recesses beneath the real printed film instead of painting their walls.
 printedFilm(host,{parent:host.parts['bottom-cover'],url:new URL('./artwork/rear-main.png',import.meta.url).href,size:[34.7666672,51.1],position:[-7.8,0,-8.275],face:'back',name:'Official Core2 v1.1 circuit adhesive film'});
 // The certification film is on the +Y white edge, offset toward -X. It
 // bridges the native mounting recess beneath it in the assembled product.
 printedFilm(host,{parent:host.parts['upper-housing'],url:new URL('./artwork/certification.png',import.meta.url).href,size:[16.1,12.1333335],position:[-8.2,27.01,0],face:'top',rotation:Math.PI,name:'Official Core2 v1.1 certification adhesive film'});
}
