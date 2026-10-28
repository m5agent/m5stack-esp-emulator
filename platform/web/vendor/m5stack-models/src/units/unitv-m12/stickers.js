import{printedArtwork}from'../../modeling/artwork.js';
const rear=new URL('./artwork/rear.png',import.meta.url).href;
const front=new URL('./artwork/front.png',import.meta.url).href;
export function addStickers(host){const a=host.unitVM12Assembly;return[...(printedArtwork(host,{target:a.label,url:rear,size:[16,20.5],position:[0,6.8,-6.39],face:'back',depth:.1,artworkKind:'reference-redraw',name:'UnitV-M12 own readable rear manufacturer film print;variable identifiers omitted'})??[]),...(printedArtwork(host,{target:a.front,url:front,size:[10,6],position:[0,-2.7,1.85],face:'front',depth:.5,artworkKind:'reference-redraw',name:'UnitV-M12 own pale M5 marking on actual CNC metal;no adhesive film'})??[])];}
