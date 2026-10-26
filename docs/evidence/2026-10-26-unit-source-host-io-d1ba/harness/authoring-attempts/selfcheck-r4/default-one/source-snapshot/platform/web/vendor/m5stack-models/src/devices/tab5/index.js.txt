import * as THREE from 'three';
import {Device,Display,Port,Button,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {grove,slab,disc,header,FACE,mesh,portQuaternion} from '../../modeling/parts.js';
import {cadButton} from '../../modeling/actuators.js';
import {usbA,usbC,microSD,audioJack} from '../../modeling/connectors.js';
import {addMainBoard} from './main-board.js';
import {addEdgeDetails} from './edge-details.js';
import {DIM} from './dimensions.js';import data from './geometry-data.js';
import {artwork} from '../../modeling/artwork.js';
export class Tab5 extends Device{
 static meta={id:'m5stack.tab5',name:'Tab5',sku:'C145',vendor:'M5Stack',size:DIM.body,keymap:{KeyP:'power',KeyR:'reset'}};
 build(){
  const parts=addCadParts(this,data,{black:materials.plastic(0xd4d6d4,{roughness:.73}),light:materials.plastic(0xbec1bf,{roughness:.83}),key:materials.plastic(0x32383a,{roughness:.7}),power:materials.plastic(0xb82b35,{roughness:.7})});
  this.add(new Button({id:'power',label:'Battery release latch · legacy power ID',mesh:parts['power-actuator'],travel:.25,axis:[0,0,1],meta:{role:'visual-control',mechanism:'battery-release-latch',legacyId:'power',electricalBehavior:false,surfaceCenter:[58.1,8,-5.5],surfaceFace:'back'}}));
  parts['battery-cover'].material=materials.plastic(0x515756,{roughness:.84});
  null;
  slab(this.body,126.2,78.4,.14,3.4,[0,0,5.91],materials.glossy(0x080a0b,{roughness:.23,clearcoat:.3}),[],.025);
  const d=DIM.display;this.add(new Display({id:'lcd',width:1280,height:720,size:[d.w,d.h],position:[0,0,d.z],touch:true,glass:{intensity:.12,roughness:.2},meta:{role:'external-framebuffer',activeAreaSource:'diagonal-derived; pending panel drawing'}}));
  disc(this.body,1.7,[59.6,0,6.12],materials.metal(0x7d8588,{roughness:.5}));disc(this.body,.8,[59.6,0,6.14],materials.glossy(0x16242b,{roughness:.08}));
  for(const x of [-40,-6])disc(this.body,.55,[x,37,6.14],materials.cavity());
  // Physical main PCB sits behind the rear expansion windows, independently of artwork.
  addMainBoard(this.body);
  // Ports placed against independent ray scans of the actual selected shell apertures.
  usbC(this,{position:[-64.02,0,-2.4],face:'left',w:8.7,h:3.1});
  usbA(this,{position:[-64.02,15,-2.5],face:'left',w:13.2,h:5.5});
  grove(this,{position:[-63.65,-26,-3.5],face:'left',w:10,h:5,color:0xbe3441});
  audioJack(this,{position:[-64.02,-13,-3.5],face:'left'});
  microSD(this,{position:[-15.25,-40.02,-2],face:'bottom',w:13,h:1.5});
  header(this.body,{position:[-38,-39.8,-3],face:'bottom',cols:5,rows:2});
  this.add(new Port({id:'gpio-ext',label:'GPIO_EXT 2x5',connector:'gpio-2x5',position:[-38,-40,-3],quaternion:portQuaternion('bottom'),hitSize:[13.2,1,5.58],meta:{role:'visual-connector',face:'bottom'}}));
  addEdgeDetails(this);
  header(this.body,{position:[9.3,0,-5.75],face:'back',cols:2,rows:15,pitch:2.54});
  const ext=new THREE.Group();ext.position.set(.7,0,-5.75);ext.quaternion.copy(FACE.back);this.body.add(ext);ext.name='Rear six-pin industrial connector housing';
  slab(ext,3.8,10.2,.7,.3,[0,0,-.6],materials.plastic(0xcbd1c8),[{w:2.7,h:8.7,r:.15}],.035);
  mesh(ext,new THREE.PlaneGeometry(2.7,8.7),materials.cavity(),[0,0,-.61]);
  for(let i=0;i<6;i++)mesh(ext,new THREE.BoxGeometry(.5,.4,.2),materials.metal(0xb7ada0),[0,(i-2.5)*1.4,-.2]);
  cadButton(this,{source:parts['main-housing'],id:'reset',label:'Reset / Boot / Power button',position:[-64,28.2,0],face:'left',w:7.4,h:7.5,r:1.1,depth:1.5,travel:.2});
  // Actual rear shells, battery bay, and side apertures come from CAD. Inserts are photo-calibrated.
  for(const x of [-58,58])for(const y of [-34,34]){const m=disc(this.body,1.4,[x,y,-6.03],materials.metal(0x8b9294));m.quaternion.copy(FACE.back);}
 }
}
export default Tab5;
