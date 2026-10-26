import {printedArtwork} from '../../modeling/artwork.js';
const educationBack=new URL('./education-cn-back.png',import.meta.url).href;
const redrawBack=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){
 const education=host.options.stickerVariant==='education-cn';
 if(!education&&host.options.stickerVariant&&host.options.stickerVariant!=='standard')return [];
 const back=education?educationBack:redrawBack;
 const variant=education?'education-cn':'standard';
 const kind=education?'official-raster':'reference-redraw';
 const panels=printedArtwork(host,{target:host.parts.housing,url:back,size:education?[16.1,16.1*256/340]:[16,12],position:[0,7,-3.8],face:'back',depth:.12,artworkKind:kind,name:education?'Thermal official Chinese education rear sticker':'Thermal rear sticker (reference redraw)'});
 for(const panel of panels??[]){panel.userData.stickerVariant=variant;panel.userData.source=kind;}return panels;
}
