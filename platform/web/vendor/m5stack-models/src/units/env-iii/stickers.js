import {printedArtwork} from '../../modeling/artwork.js';
const educationBack=new URL('./education-cn-back.png',import.meta.url).href;
const redrawBack=new URL('./reference-redraw-back.png',import.meta.url).href;
export function addStickers(host){
 const education=host.options.stickerVariant==='education-cn';
 if(!education&&host.options.stickerVariant&&host.options.stickerVariant!=='standard')return [];
 const back=education?educationBack:redrawBack;
 const variant=education?'education-cn':'standard';
 const kind=education?'official-raster':'reference-redraw';
 const rear=host.parts.rear;
 for(const old of [...rear.children])if(old.geometry?.type==='PlaneGeometry'&&old.geometry.parameters.width===16.3&&old.geometry.parameters.height===12){old.removeFromParent();old.geometry.dispose();old.material.map?.dispose();old.material.dispose();}
 const owner=host.body;if(host.unitFrame)host.body=host.unitFrame.object3d;
 try{
  const panels=printedArtwork(host,{target:rear.getObjectByName('rear-shell'),url:back,size:[16,12],position:[0,7,-4],face:'back',depth:.12,artworkKind:kind,name:education?'ENV III official Chinese education rear sticker':'ENV III rear sticker (reference redraw)'});
  for(const panel of panels??[]){panel.userData.stickerVariant=variant;panel.userData.source=kind;}return panels;
 }finally{host.body=owner;}
}
