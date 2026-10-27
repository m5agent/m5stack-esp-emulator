import * as THREE from 'three';
import {Device,Display,Port,Button,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {grove,slab,disc,header,FACE,mesh,portQuaternion} from '../../modeling/parts.js';
import {cadButton} from '../../modeling/actuators.js';
import {usbA,usbC,microSD,audioJack} from '../../modeling/connectors.js';
import {addMainBoard} from './main-board.js';
import {addEdgeDetails} from './edge-details.js';
import {DIM} from './dimensions.js';import data from './geometry-data.js';
import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
export class Tab5 extends Device{
 static meta={id:'m5stack.tab5',name:'Tab5',sku:'C145',vendor:'M5Stack',size:DIM.body,keymap:{KeyP:'power',KeyR:'reset'}};
 build(){
  const parts=addCadParts(this,data,{black:materials.plastic(0xd4d6d4,{roughness:.73}),light:materials.plastic(0xbec1bf,{roughness:.83}),key:materials.plastic(0x32383a,{roughness:.7}),power:materials.plastic(0xb82b35,{roughness:.7})});
  this.add(new Button({id:'power',label:'Battery release latch · legacy power ID',mesh:parts['power-actuator'],travel:.25,axis:[0,0,1],meta:{role:'visual-control',mechanism:'battery-release-latch',legacyId:'power',electricalBehavior:false,surfaceCenter:[58.1,8,-5.5],surfaceFace:'back'}}));
  parts['battery-cover'].material=materials.plastic(0x515756,{roughness:.84});
  // The complete source bridges the cover's four round recesses; preserve its
  // two die-cut circles and keep the separate six-pin connector unobstructed.
  printedFilm(this,{parent:parts['back-cover'],url:new URL('./artwork/rear.png',import.meta.url).href,size:[68.6,76.65],position:[-27.9,0,-6.02],face:'back',holes:[{cx:-28.6,cy:0,w:3.8,h:10.2,r:.3}],name:'Tab5 official ST7123 rear circuit sticker'});
  // The BATTERY / M-BUS print belongs inside the bay, below the separate
  // unprinted mechanical battery cover visible in the assembled reference.
  printedArtwork(this,{target:parts['main-housing'],url:new URL('./artwork/battery-bay.png',import.meta.url).href,size:[32.4,65.87],position:[36.3,4.7,.5],face:'back',depth:1.2,name:'Tab5 official battery bay sticker'});
  printedArtwork(this,{target:parts['main-housing'],url:new URL('./artwork/name.png',import.meta.url).href,size:[37.8,6.99],position:[36.5,-35.5,-6],face:'back',depth:.4,name:'Tab5 official rear name sticker'});
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
  for(const [file,size,position,face]of [
   ['usb-a',[13.1,3.68],[-64,15,3.2],'left'],
   ['usb-c',[8.2,5.66],[-64,0,2.6],'left'],
   ['headset',[9.8,9.23],[-64,-13,.6],'left'],
   ['port-a',[10.2,5.39],[-64,-26,2.2],'left'],
   ['gpio',[13.3,5.3],[-38,-40,2.5],'bottom'],
   ['certification',[40.7,9.74],[22,-40,.1],'bottom']
  ])printedArtwork(this,{target:parts['main-housing'],url:new URL(`./artwork/${file}.png`,import.meta.url).href,size,position,face,depth:.45,name:`Tab5 official ${file} sticker`});
  // Actual rear shells, battery bay, and side apertures come from CAD. Inserts are photo-calibrated.
  for(const x of [-58,58])for(const y of [-34,34]){const m=disc(this.body,1.4,[x,y,-6.03],materials.metal(0x8b9294));m.quaternion.copy(FACE.back);}
 }
}
export default Tab5;
