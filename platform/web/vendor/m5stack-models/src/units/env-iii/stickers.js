import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./education-cn-back.png',import.meta.url).href;
export function addStickers(host){
 if(host.options.stickerVariant!=='education-cn')return [];
 const rear=host.parts.rear;
 for(const old of [...rear.children])if(old.geometry?.type==='PlaneGeometry'&&old.geometry.parameters.width===16.3&&old.geometry.parameters.height===12){old.removeFromParent();old.geometry.dispose();old.material.map?.dispose();old.material.dispose();}
 const owner=host.body;if(host.unitFrame)host.body=host.unitFrame.object3d;
 try{
  const panels=printedArtwork(host,{target:rear.getObjectByName('rear-shell'),url:back,size:[16,12],position:[0,7,-4],face:'back',depth:.12,name:'ENV III official Chinese education rear sticker'});
  for(const panel of panels??[])panel.userData.stickerVariant='education-cn';return panels;
 }finally{host.body=owner;}
}
