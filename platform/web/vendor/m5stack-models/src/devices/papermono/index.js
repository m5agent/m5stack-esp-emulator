import {Device,Button,Led,materials} from '../../core/index.js';
import {PaperDisplay} from '../../modeling/PaperDisplay.js';
import {addCadParts} from '../../modeling/cad.js';
import {isolateActuatorMaterials} from '../../modeling/actuators.js';
import {slab,FACE} from '../../modeling/parts.js';
import {usbC,microSD} from '../../modeling/connectors.js';
import {addAssembly,rgbGuide} from './assembly.js';
import {printedArtwork} from '../../modeling/artwork.js';
import {DIM} from './dimensions.js';
import data from './geometry-data.js';
export class PaperMono extends Device {
 static meta={id:'m5stack.papermono',name:'PaperMono',sku:'C153',vendor:'M5Stack',size:DIM.body,keymap:{ArrowUp:'key1',ArrowDown:'key2',KeyP:'power'}};
 build(){
  const parts=addCadParts(this,data,{shell:materials.plastic(0xcfd2cf,{roughness:.78,clearcoat:.015}),key:materials.plastic(0x444b4d,{roughness:.65}),power:materials.plastic(0xb24b3c,{roughness:.65})});
  for(const [part,id,label] of [['key-up','key1','Up key'],['key-down','key2','Down key'],['power-key','power','Power key']])this.add(new Button({id,label,mesh:isolateActuatorMaterials(parts[part]),travel:.2,axis:[1,0,0],meta:{role:'visual-control'}}));
  const d=DIM.display;
  // Official STL contains the chassis, not the thin front cover. The photo-calibrated
  // cover closes the exposed electronics while retaining an actual screen opening.
  slab(this.body,59.7,99.7,.35,2.8,[.5,0,3.66],materials.plastic(0xcfd2cf,{roughness:.82}),[{w:d.w+.2,h:d.h+.2,r:.2,cx:d.cx-.5,cy:d.cy}],.06).name='Paper front cover';
  addAssembly(this,d);
  slab(this.body,d.w+.3,d.h+.3,.035,.2,[d.cx,d.cy,3.92],materials.plastic(0xb3b8b4,{roughness:.9}),[],.01);
  this.add(new PaperDisplay({id:'lcd',label:'3.97-inch 480×800 paper display',width:480,height:800,size:[d.w,d.h],position:[d.cx,d.cy,d.z],touch:true,meta:{role:'external-framebuffer',surface:'reflective',activeAreaSource:'derived; pending panel drawing'}}));
  usbC(this,{...DIM.usb,face:'bottom',depth:4.5});
  microSD(this,{...DIM.sd,face:'left',depth:6.5});
  this.add(new Led({id:'rgb',label:'RGB light guide',mesh:rgbGuide(),position:DIM.rgb.position,quaternion:FACE.left,radius:.45,glowSize:3,meta:{role:'externally-driven-visual'}}));
  // Orthographic rear reference: the NFC cover starts below the complete
  // circuit sticker. Keep its original lower edge and thickness.
  slab(this.body,59.6,34.65,.6,3.4,[.5,-31.725,-4.06],materials.glossy(0x151a1d,{roughness:.25,clearcoat:.25}),[],.035).name='NFC rear molded cover';
  printedArtwork(this,{target:parts['paper-shell'],url:new URL('./artwork/rear.png',import.meta.url).href,size:[57.5,62.9447],position:[.5,18.2,-3.8],face:'back',depth:.5,name:'PaperMono official rear circuit sticker'});
 }
}
export default PaperMono;
