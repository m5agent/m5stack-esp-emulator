import {printedArtwork} from '../../modeling/artwork.js';
const educationBack=new URL('./education-cn-back.png',import.meta.url).href;
const redrawBack=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){
 const education=host.options.stickerVariant==='education-cn';
 if(!education&&host.options.stickerVariant&&host.options.stickerVariant!=='standard')return [];
 const back=education?educationBack:redrawBack;
 const variant=education?'education-cn':'standard';
 const kind=education?'official-raster':'reference-redraw';
 const panels=printedArtwork(host,{target:host.parts['Scroll back shell'],url:back,size:education?[19.8,13.8]:[19.7,13.726513671874999],position:[0,7,-3.8],face:'back',depth:.12,artworkKind:kind,name:education?'Scroll official Chinese education rear sticker':'Scroll rear sticker (reference redraw)'});
 for(const panel of panels??[]){panel.userData.stickerVariant=variant;panel.userData.source=kind;}return panels;
}
