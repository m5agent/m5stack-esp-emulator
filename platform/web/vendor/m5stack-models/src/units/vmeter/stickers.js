import{printedArtwork,printedFilm}from'../../modeling/artwork.js';
const front=new URL('./reference-redraw-front.png',import.meta.url).href,back=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){
 // The actual front adhesive label bridges the native moulded clip slots.
 // The unchanged slots remain backed by the physical PCB/electronic assembly.
 const f=printedFilm(host,{url:front,size:[15.7,26.7],position:[0,2.3,3.82],artworkKind:'reference-redraw',name:'VMeter reference-redraw front V Meter polarity label'});
 const b=printedArtwork(host,{target:host.parts['VMeter complete native rear shell'],url:back,size:[16,38],position:[0,4,-3.8],face:'back',depth:.18,artworkKind:'reference-redraw',name:'VMeter reference-redraw rear isolated topology label'})??[];
 return[...(f?[f]:[]),...b];
}
