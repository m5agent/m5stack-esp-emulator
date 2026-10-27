import {printedArtwork} from '../../modeling/artwork.js';
const back=new URL('./official-back.png',import.meta.url).href;
export function addStickers(host){
 const rear=host.parts.rear;
 // Retire the old hand-drawn label; the original artwork now supplies the print.
 for(const old of [...rear.children])if(old.geometry?.type==='PlaneGeometry'&&old.geometry.parameters.width===16.3&&old.geometry.parameters.height===37.5){
  old.removeFromParent();old.geometry.dispose();old.material.map?.dispose();old.material.dispose();
 }
 const owner=host.body;
 if(host.unitFrame)host.body=host.unitFrame.object3d;
 try{return printedArtwork(host,{target:rear.getObjectByName('rear-shell'),url:back,size:[16,36],position:[0,5.4,-4],face:'back',depth:.12,name:'Ultrasonic I2C official rear sticker'});}
 finally{host.body=owner;}
}
