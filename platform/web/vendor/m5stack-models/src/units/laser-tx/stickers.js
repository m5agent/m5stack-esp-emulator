import{printedArtwork}from'../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href,back=new URL('./reference-redraw-back.png',import.meta.url).href;
/** New code-drawn artwork from exact U066 official photographs; no photographic pixels. */
export function addStickers(host){const target=host.parts['Laser TX complete native assembled shell'];return[...(printedArtwork(host,{target,url:front,size:[20,14],position:[0,7,3.8],face:'front',depth:.14,name:'Laser TX reference-redrawn LASER BEAM front print',artworkKind:'reference-redraw'})??[]),...(printedArtwork(host,{target,url:back,size:[16.2,12.2],position:[0,7,-3.8],face:'back',depth:.14,name:'Laser TX reference-redrawn wavelength power and OUT pin label',artworkKind:'reference-redraw'})??[])];}
