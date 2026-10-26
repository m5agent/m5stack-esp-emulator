import {Device,Button,materials} from '../../core/index.js';
import {PaperDisplay} from '../../modeling/PaperDisplay.js';
import {addCadParts} from '../../modeling/cad.js';
import {isolateActuatorMaterials} from '../../modeling/actuators.js';
import {grove,slab} from '../../modeling/parts.js';
import {usbC,microSD} from '../../modeling/connectors.js';
import {addAssembly} from './assembly.js';
import {printedArtwork} from '../../modeling/artwork.js';
import {DIM} from './dimensions.js';
import data from './geometry-data.js';
export class PaperColor extends Device {
 static meta={id:'m5stack.papercolor',name:'PaperColor',sku:'C151',vendor:'M5Stack',size:DIM.body,keymap:{KeyA:'key1',KeyB:'key2',KeyC:'key3',KeyP:'power'}};
 build(){
  const parts=addCadParts(this,data,{shell:materials.plastic(0xe0e3de,{roughness:.79,clearcoat:.01}),key:materials.plastic(0x586166,{roughness:.68}),lens:materials.plastic(0xc3cac4,{roughness:.5,clearcoat:.14,transmission:.14,thickness:.8})});
  for(const [part,id,axis] of [['key-a','key1',[1,0,0]],['key-b','key2',[1,0,0]],['key-c','key3',[0,-1,0]],['power-key','power',[1,0,0]]])this.add(new Button({id,label:id,mesh:isolateActuatorMaterials(parts[part]),travel:.18,axis,meta:{role:'visual-control'}}));
  const d=DIM.display;
  slab(this.body,68.9,102.5,.35,2.8,[.4165,-.441,3.9],materials.plastic(0xe0e3de,{roughness:.82}),[{w:d.w+.2,h:d.h+.2,r:.2,cx:d.cx-.4165,cy:d.cy+.441}],.06).name='Paper front cover';
  addAssembly(this,d);
  slab(this.body,d.w+.3,d.h+.3,.035,.2,[d.cx,d.cy,4.21],materials.plastic(0xbabfba,{roughness:.92}),[],.01);
  this.add(new PaperDisplay({id:'lcd',label:'4-inch 400×600 E Ink display',width:400,height:600,size:[d.w,d.h],position:[d.cx,d.cy,d.z],touch:false,meta:{role:'external-framebuffer',surface:'reflective',activeAreaSource:'derived; pending panel drawing'}}));
  usbC(this,{...DIM.usb,face:'bottom',depth:4.5});grove(this,{...DIM.grove,face:'bottom'});
  microSD(this,{...DIM.sd,face:'left',depth:6.5});
  for(const [file,size,position]of [['rear-upper',[66.7,38.87],[.4165,31.1,-4.05]],['rear-lower',[66.7,38.75],[.4165,-30.7,-4.05]]])printedArtwork(this,{target:parts['paper-shell'],url:new URL(`./artwork/${file}.png`,import.meta.url).href,size,position,face:'back',depth:.5,name:`PaperColor official ${file} sticker`});
  printedArtwork(this,{target:[parts['paper-shell'],this.body.getObjectByName('Bottom aperture molded insert')],url:new URL('./artwork/bottom.png',import.meta.url).href,size:[31.9,5.97],position:[.4165,-51.8,.3],face:'bottom',depth:.9,name:'PaperColor official bottom badge'});
 }
}
export default PaperColor;
