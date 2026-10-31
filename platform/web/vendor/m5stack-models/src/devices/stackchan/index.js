import * as THREE from 'three';
import {CoreS3} from '../cores3/CoreS3.js';
import {Device,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {grove,slab,screw} from '../../modeling/parts.js';
import {DIM} from './dimensions.js';import data from './geometry-data.js';
import {addRearAssembly,addTopBoard,addNeckAdapter} from './rear-assembly.js';
import {VisualJoint} from '../../core/components/VisualJoint.js';
import {addMotionMechanics} from './motion-mechanics.js';
import {usbC} from '../../modeling/connectors.js';
import {PitchHarness} from './PitchHarness.js';
import {addTouchLed} from './touch-led.js';
import {printedArtwork} from '../../modeling/artwork.js';
export class StackChan extends Device{
 static meta={id:'m5stack.stackchan',name:'StackChan',sku:'K151',vendor:'M5Stack',size:DIM.body,keymap:{KeyP:'power'}};
 build(){
  addCadParts(this,data,{shell:materials.plastic(0xbfc3c1,{roughness:.76}),dark:materials.plastic(0x303638,{roughness:.83}),'white-cover':materials.plastic(0xbdc5bf,{roughness:.83}),'grey-cover':materials.plastic(0x6f7974,{roughness:.83})});
  const rear=addRearAssembly(this);
  const top=addTopBoard(this);
  // StackChan has its own exterior certification and side labels. The exposed
  // rear assembly is distinct from a standalone CoreS3 shield sticker.
  const core=new CoreS3({artwork:false,lcdCenterY:DIM.lcd.cy});this.body.add(core.root);core.root.position.fromArray(DIM.corePosition);
  // Reuse the exact visual module, preserving public lcd/button/port IDs at the top level.
  for(const c of core.components.values())this.add(c,core.body);
  core.components.clear();
  const baseUsb=usbC(this,{id:'base-usb',position:[0,-27.7,-30.77],face:'back',w:8.7,h:3.1,depth:6.5});
  // The two extra Grove ports occupy the actual top-shell apertures beside the
  // CoreS3 rear edge; gallery-16 shows black PORT.B and blue PORT.C.
  const headParts=[this.parts['head-shell'],rear,top,core.root];
  for(const x of [-11,11]){
   const id=x<0?'port-b':'port-c';
   const connector=grove(this,{id,position:[x,35.27,13.0],face:'top',w:9.8,h:5.4,color:x<0?0x252d2b:0x197e93});connector.name=`Head Grove ${x<0?'B':'C'}`;
   connector.children[5].name=`${connector.name} backstop`;for(let i=0;i<4;i++)connector.children[6+i].name=`${connector.name} contact ${i+1}`;
   headParts.push(connector,this.port(id).object3d);
  }
  const rearFittings=new THREE.Group();rearFittings.name='Neck lower rear fittings';this.body.add(rearFittings);
  // Original gray-cover ears seat on the cradle's two coaxial M2 bores.
  // Their recessed back faces are Z-22.05, not the outer plate's Z-24.05.
  for(const x of [-10.749219,11.250781])screw(rearFittings,[x,-21.75,-22.06],'back',1.5);
  // This small appearance insert belongs to the cradle's genuine central
  // opening; it does not follow a guessed gray-cover plane or emit light.
  slab(rearFittings,1.5,3,.3,.25,[.250781,-21.75,-24.94],materials.glossy(0x843b1c,{roughness:.2}),[],.04).name='Cradle central window appearance insert';
  const touchLed=addTouchLed(this);headParts.push(touchLed.group);
  const mechanics=addMotionMechanics(this),adapter=addNeckAdapter(this,mechanics);
  headParts.push(...mechanics.headParts);
  // The base/USB stay fixed; the neck yaws, and only the head pitches above it.
  // Pitch axis is fitted to coaxial circular faces of the official ServoBody:
  // Y=6.65, Z=-2.  Positive pitch raises the face from the supplied front pose.
  const original=[...this.body.children],fixed=new Set([this.parts.base,this.parts['base-bottom'],baseUsb,this.port('base-usb').object3d,...mechanics.fixedParts]);
  const pitch=this.add(new VisualJoint({id:'pitch',label:'StackChan head pitch',position:[0,6.65,-2],axis:[-1,0,0],limitsDeg:[0,90],meta:{axisEvidence:'Official ServoBody coaxial bores fit Y6.65/Z-2; horizontal X axis',rangeEvidence:'Official total travel 90 degrees; viewer zero is the supplied front pose, positive raises the head; absolute hardware calibration is unconfirmed'}}));
  const yaw=this.add(new VisualJoint({id:'yaw',label:'StackChan horizontal head / neck',position:[0,-24.15,-2],axis:[0,1,0],continuous:true,meta:{axisEvidence:'Official 360-degree horizontal rotation; axis follows the lower neck CAD circular arcs at X0/Z-2',demoRpmMax:20}}));
  pitch.adopt(...headParts);
  yaw.adopt(...original.filter(o=>!fixed.has(o)&&!headParts.includes(o)),pitch.object3d);
  const harness=this.add(new PitchHarness({id:'pitch-harness',label:'StackChan seven-wire visual loom',upper:rear.upperHarness,lower:adapter.lowerHarness,pitch,meta:{role:'visual-cross-joint-harness',source:'Official Power/Adapter CON4 and rear photo; hidden routing inferred'}}));
  yaw.adopt(harness.object3d);harness.update();
  for(const [x,face]of [[-27,'left'],[27,'right']])printedArtwork(this,{target:this.parts['head-shell'],url:new URL('./artwork/side.png',import.meta.url).href,size:[40.5,5.45],position:[x,8.25,11.2],face,depth:.45,name:`StackChan official ${face} head sticker`});
  printedArtwork(this,{target:core.parts['core-module-shell'],url:new URL('./artwork/certification.png',import.meta.url).href,size:[16,12.28],position:[-7.5,34.95,23.2],face:'top',rotation:Math.PI,depth:.7,name:'StackChan official head certification sticker'});
  printedArtwork(this,{target:this.parts['base-bottom'],url:new URL('./artwork/bottom.png',import.meta.url).href,size:[32.8,35.86],position:[0,-35,-2.5],face:'bottom',depth:.7,name:'StackChan official fixed base bottom sticker'});
  this.stackchanAssembly={rear,adapter,mechanics,harness,baseUsb,touchLed};
 }
}
export default StackChan;
