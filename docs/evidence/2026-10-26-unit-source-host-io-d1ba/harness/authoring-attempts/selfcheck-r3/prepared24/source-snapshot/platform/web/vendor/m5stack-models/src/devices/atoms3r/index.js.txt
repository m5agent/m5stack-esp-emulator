import * as THREE from 'three';
import {Device,Display,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {grove,header,slab,FACE,mesh,disc} from '../../modeling/parts.js';
import {cadButton,physicalButton} from '../../modeling/actuators.js';
import {usbC} from '../../modeling/connectors.js';
import {DIM} from './dimensions.js';
import data from './geometry-data.js';
export class AtomS3R extends Device {
 static meta={id:'m5stack.atoms3r',name:'AtomS3R',sku:'C126',size:[24,24,12.9],vendor:'M5Stack',keymap:{Space:'button'}};
 build(){
  const parts=addCadParts(this,data,{light:materials.plastic(0xc7cbc9,{roughness:.73,clearcoat:.01})});
  // The CAD contains only the two molded shells. Real boards and connector bodies
  // close its open assembly windows; a framebuffer plane cannot substitute for them.
  const lcdModule=slab(this.body,18.9,20,3.0,.7,[0,.1,3.1],materials.plastic(0x20282b,{roughness:.82}),[],.12);lcdModule.name='LCD module body';
  // The connector receptacles pass through board clearances, so their real bores
  // remain recessed instead of ending on an intersecting green PCB surface.
  const headerClearances=[[7.65,-2.70,5],[-7.65,-3.97,4]].flatMap(([x,y,count])=>Array.from({length:count},(_,i)=>({w:1.85,h:1.85,r:.12,cx:x,cy:y+(i-(count-1)/2)*2.54-.1})));
  slab(this.body,20.5,21.8,.8,.8,[0,.1,-6.30],materials.plastic(0x314b40,{roughness:.9}),[{w:2.2,h:2.2,r:1.1,cx:0,cy:-.1},...headerClearances],.08).name='Rear main PCB';
  const mountFloor=disc(this.body,1.08,[0,0,-5.45],materials.cavity());mountFloor.quaternion.copy(FACE.back);mountFloor.name='M2 mounting blind-hole floor';
  slab(this.body,12.3,15.2,.15,.2,[0,4.4,-6.44],materials.plastic(0xc9cec8,{roughness:.87}),[{w:2.2,h:2.2,r:1.1,cx:0,cy:-4.4}],.025).name='Rear PCB retaining plate';
  const antenna=slab(this.body,18.2,2.3,.7,.2,[0,-11.3,4.15],materials.plastic(0x21272a,{roughness:.79}),[],.04);antenna.quaternion.copy(FACE.bottom);antenna.name='3D antenna body';
  const edge=slab(this.body,10.2,.9,.6,.1,[0,-11.4,-.9],materials.plastic(0x304936,{roughness:.9}),[],.03);edge.quaternion.copy(FACE.bottom);
  const lcdBezel=slab(this.body,17.2,17.2,.15,.6,[-.0,0,6.02],materials.cavity(),[],.03);
  const lcd=this.add(new Display({id:'lcd',label:'0.85-inch 128×128 LCD',width:128,height:128,size:[DIM.lcd.active,DIM.lcd.active],position:DIM.lcd.position,pixelEffect:true,touch:false,glass:{size:[16.3,16.3],offset:.02,intensity:.2,roughness:.14},meta:{role:'external-framebuffer'}}));
  usbC(this,{...DIM.usb,face:'bottom',depth:3.5});grove(this,DIM.grove);
  // The rectangular package behind the USB capsule fills the shell's corner
  // clearances. Its actual capsule bore stays open; gallery-06 shows this seat.
  const usbSeat=new THREE.Group();usbSeat.position.set(0,-11.75,1.15);usbSeat.quaternion.copy(FACE.bottom);usbSeat.name='USB-C package seat';this.body.add(usbSeat);
  slab(usbSeat,9.6,3.5,2.6,.4,[0,0,-2.6],materials.plastic(0x18201b,{roughness:.84}),[{w:8.6,h:2.9,r:1.45}],.04).name='USB-C rectangular package surround';
  // Black connector side seats and stamped retaining tabs occupy the narrow
  // side windows around the white Grove body, independently of the real mouth.
  for(const side of [-1,1]){
   mesh(this.body,new THREE.BoxGeometry(1.2,4.0,4.1),materials.plastic(0x151e18,{roughness:.87}),[side*5.75,-9.2,-3.5],'Grove connector side seat');
   mesh(this.body,new THREE.BoxGeometry(.32,1.2,2.8),materials.metal(0x9aa6a0,{roughness:.49}),[side*5.25,-11.0,-3.3],'Grove retaining clip');
  }
  const screenKey=new THREE.Group();screenKey.name='Pressable LCD and bezel assembly';screenKey.add(lcdModule,lcdBezel,lcd.object3d);
  physicalButton(this,{id:'button',label:'Front programmable LCD key',mesh:screenKey,travel:.18,meta:{surfaceCenter:[0,0,6.32],surfaceFace:'front'}});
  cadButton(this,{source:parts['rear-shell'],id:'reset',label:'Side reset key',position:[-12,5,-1],face:'left',w:4,h:7.4,r:.3,depth:1.8,travel:.16});
  header(this.body,{position:[7.65,-2.70,-6.2],cols:1,rows:5});
  header(this.body,{position:[-7.65,-3.97,-6.2],cols:1,rows:4});
 }
}
export default AtomS3R;
