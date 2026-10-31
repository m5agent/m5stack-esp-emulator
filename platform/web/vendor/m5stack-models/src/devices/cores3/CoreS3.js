import * as THREE from 'three';
import {Device,Display,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {socket,grove,header,slab,disc,FACE,screw,mesh,portQuaternion} from '../../modeling/parts.js';
import {cadButton,physicalButton} from '../../modeling/actuators.js';
import coreData from './geometry-data.js';
import dinData from './geometry-data-din.js';
import {DIM} from './dimensions.js';
import {printedArtwork,printedFilm} from '../../modeling/artwork.js';
/** Independently rebuilt from the official structure. No geometry is reused from the rejected legacy CoreS3 model. */
export class CoreS3 extends Device {
 static meta={id:'m5stack.cores3',name:'CoreS3',sku:'K128',vendor:'M5Stack',size:[54,54,15.5],keymap:{KeyP:'power'}};
 get meta(){return {...CoreS3.meta,size:this.options.dinBase?[54,69.284,31.5]:[54,54,15.5],configuration:this.options.dinBase?'CoreS3 + DinBase':'CoreS3 module'};}
 build({dinBase=false,touch=true,lcdCenterY=DIM.lcd.cy}={}){
  const parts=addCadParts(this,dinBase?dinData:coreData,{black:materials.plastic(0x303438,{roughness:.76,clearcoat:.015})});
  const front=dinBase?15.75:7.75;
  const lcdBody=slab(this.body,44.6,34.3,1.5,1.1,[0,lcdCenterY,front-1.8],materials.plastic(0x171c1d),[],.08);lcdBody.name='LCD module backing';
  // The official CAD is the enclosure; this acoustic housing sits behind its real grille holes.
  const speaker=new THREE.Group();speaker.position.set(25.25,5,front-7.95);speaker.quaternion.copy(FACE.right);speaker.name='Speaker acoustic housing';this.body.add(speaker);
  slab(speaker,26,5.8,1.2,.7,[0,0,-1.2],materials.plastic(0x121516,{roughness:1}),[],.06);
  slab(this.body,DIM.glass.w,DIM.glass.h,.08,DIM.glass.r,[0,0,front-.04],materials.glossy(0x090c0d,{roughness:.21,clearcoat:.3}),[],.025);
  this.add(new Display({id:'lcd',label:'2.0-inch LCD · 320×240',width:320,height:240,size:[DIM.lcd.w,DIM.lcd.h],position:[0,lcdCenterY,front+.06],touch,pixelEffect:true,glass:{size:[42.4,32.2],offset:.015,intensity:.15,roughness:.16},meta:{role:'external-framebuffer',physicalAreaSource:'derived from 2.0-inch specification; pending panel drawing'}}));
  const c=DIM.camera;disc(this.body,c.radius+.35,[c.x,c.y,front+.07],materials.metal(0xa35c31,{roughness:.44}));disc(this.body,c.radius,[c.x,c.y,front+.09],materials.glossy(0x131b22,{roughness:.1}));disc(this.body,.7,[c.x,c.y,front+.105],materials.glossy(0x193042,{roughness:.08}));
  for(const x of [-20.8,20.8])disc(this.body,.4,[x,-20.8,front+.08],materials.cavity());
  slab(this.body,3.5,2.7,.12,.5,[8.8,-20.8,front+.045],materials.glossy(0x171529,{roughness:.16}),[],.025);
  disc(this.body,.48,[13,-20.8,front+.08],materials.plastic(0x9ba6a3));
  // Interface inserts are separate from the official shell. Their local positions remain photo-calibrated, pending side-view QA.
  socket(this,{position:[-27.02,0,front-8.125],face:'left',w:8.5,h:3});
  grove(this,{position:[-27.02,-14,front-9],face:'left',w:9.8,h:4.9,color:0x9c1629});
  const molded=parts[dinBase?'assembled-core-din':'core-module-shell'];
  cadButton(this,{source:molded,id:'power',label:'Side power key',position:[-27,13,front-7.85],face:'left',w:5.6,h:9.1,r:1.6,depth:1.8,travel:.18});
  cadButton(this,{source:molded,id:'reset',label:'Reset / download key',position:[15.5,-27,front-7.55],face:'bottom',w:7,h:5.7,r:2.2,depth:1.8,travel:.18});
  const sd=new THREE.Mesh(new THREE.PlaneGeometry(12,1.15),materials.cavity());sd.position.set(-6.5,-27.025,front-8.25);sd.quaternion.copy(FACE.bottom);this.body.add(sd);
  if(dinBase)this.#baseBack();else this.#moduleBack();
  printedArtwork(this,{target:molded,url:new URL('./artwork/certification.png',import.meta.url).href,size:[16,12.3],position:[7.5,27,front-7.45],face:'top',rotation:Math.PI,name:'CoreS3 official certification sticker'});
  if(dinBase){
   for(const [file,size,position,face] of [
    ['din-name',[42,10],[27,0,-8.5],'right'],
    ['din-dc',[8.8,5.9],[0,-27,-3.1],'bottom'],
    ['din-power',[7.9,5.7],[9,-27.13,-2.5],'bottom'],
    ['port-c',[10,3.8],[-11,27,-7.4],'top'],
    ['port-b',[10,3.8],[11,27,-7.4],'top']
   ]){
    const print={url:new URL(`./artwork/${file}.png`,import.meta.url).href,size,position,face,name:`CoreS3 official ${file} sticker`};
    // This fixed adhesive label has the supplied rectangular actuator window;
    // the moving switch remains visible and accessible through that window.
    if(file==='din-power')printedFilm(this,{...print,parent:this.body.getObjectByName('DinBase power switch mounting frame'),holes:[{w:4.3,h:2.4,r:0}]});
    else printedArtwork(this,{...print,target:molded,depth:.45});
   }
  }
 }
 #moduleBack(){
  const pcb=materials.plastic(0x252b28,{roughness:.86,clearcoat:0}),board=slab(this.body,49,49,.45,3,[0,0,-4.9],pcb,[],.08);board.name='CoreS3 rear main PCB';
  for(const x of [-21,21])header(this.body,{position:[x,0,-7.02],cols:1,rows:15});
  printedArtwork(this,{target:board,url:new URL('./artwork/rear.png',import.meta.url).href,size:[32.4,41.5],position:[0,-2.2,-4.9],face:'back',name:'CoreS3 official shield circuit sticker'});
  for(const [x,y] of [[15.8,2.65],[-16.16,3.46]]){
   mesh(this.body,new THREE.CylinderGeometry(2.8,2.8,2.5,40).rotateX(Math.PI/2),materials.metal(0xafb4b6,{roughness:.5}),[x,y,-6.1]);
   const cap=disc(this.body,2.5,[x,y,-7.37],materials.plastic(0xc5c7c3));cap.quaternion.copy(FACE.back);
  }
  slab(this.body,16.5,6.2,1.5,.5,[-2,19.1,-6.5],materials.metal(0x909797,{roughness:.52}),[],.1);
  const sd=mesh(this.body,new THREE.PlaneGeometry(13.5,1.1),materials.cavity(),[-2,19.1,-6.53]);sd.quaternion.copy(FACE.back);
  for(const x of [-21,21])for(const y of [-21,21])screw(this.body,[x,y,-7.08],'back',1.5);
 }
 #baseBack(){
  // Right-angle connectors and boards are absent from the selected enclosure STL.
  // Their positions follow the official apertures and photos gallery-04/06/08.
  const corePcb=slab(this.body,49,49,.7,3,[0,0,3.1],materials.plastic(0x252b28,{roughness:.86,clearcoat:0}),[],.05);corePcb.name='Core main PCB';
  const holes=[[-12,0,2],[12,0,2],[0,-12,1.5],[0,12,1.5],[-20,0,1.6],[20,0,1.6],...[-21,21].flatMap(x=>[-21,21].map(y=>[x,y,1.8]))].map(([cx,cy,r])=>({w:r*2,h:r*2,r,cx,cy}));
  const board=slab(this.body,49,49,.8,3,[0,0,-5.8],materials.plastic(0x202b25,{roughness:.88,clearcoat:0}),holes,.05);board.name='DinBase proto PCB';
  // Transparent reference silk belongs to the real internal PCB, beneath the
  // removable base cover. It cannot fill its mounting holes or stand in for pads.
  for(const panel of printedArtwork(this,{target:board,url:new URL('./artwork/reference-redraw-din-pcb.png',import.meta.url).href,size:[49,49],position:[0,0,-5.8],face:'back',depth:.12,artworkKind:'reference-redraw',name:'DinBase internal PCB silk (partial reference redraw)'})??[])panel.userData.source='reference-redraw';
  grove(this,{id:'grove-c',position:[-11,27.02,-2.1],face:'top',w:10.4,h:5.1,color:0x008ba6});
  grove(this,{id:'grove-b',position:[11,27.02,-2.1],face:'top',w:10.4,h:5.1,color:0x171a1b});
  const dc=new THREE.Group();dc.position.set(-10,-27.02,-3.1);dc.quaternion.copy(FACE.bottom);dc.name='DinBase DC barrel jack';this.body.add(dc);
  slab(dc,10.2,7,8,.4,[0,0,-8.05],materials.plastic(0x111516),[{w:4.8,h:4.8,r:2.4}],.05);
  const ring=new THREE.Shape();ring.absarc(0,0,3.1,0,Math.PI*2,false);const bore=new THREE.Path();bore.absarc(0,0,2.4,0,Math.PI*2,true);ring.holes.push(bore);
  mesh(dc,new THREE.ExtrudeGeometry(ring,{depth:.6,bevelEnabled:false,curveSegments:48}),materials.plastic(0x090c0d),[0,0,-.45]);
  disc(dc,2.4,[0,0,-7.5],materials.cavity());mesh(dc,new THREE.CylinderGeometry(.55,.55,3,24).rotateX(Math.PI/2),materials.metal(0xb1b5b4,{roughness:.35}),[0,0,-3]);
  this.add(new Port({id:'dc',label:'DinBase DC input · 9–24 V',connector:'dc-barrel',position:[-10,-27.02,-3.1],quaternion:portQuaternion('bottom'),hitSize:[10.2,1,7],meta:{role:'visual-connector',face:'bottom'}}));
  const sw=new THREE.Group();sw.position.set(9,-27.02,-2.5);sw.quaternion.copy(FACE.bottom);sw.name='DinBase power switch';this.body.add(sw);
  slab(sw,8.6,5.3,3,.35,[0,0,-3.05],materials.plastic(0x151818),[],.04).name='DinBase power switch mounting frame';
  const slider=new THREE.Group();slider.name='DinBase movable power slider';
  slab(slider,4.2,3.2,.9,.2,[-1.5,0,-.9],materials.plastic(0x303536),[],.03);
  for(let x=-3;x<=0;x+=.6)mesh(slider,new THREE.BoxGeometry(.16,2.7,.12),materials.plastic(0x171c1d),[x,0,.03]);
  physicalButton(this,{id:'din-power',label:'DinBase power slider · visual detents only',mesh:slider,position:[9,-27.02,-2.5],quaternion:FACE.bottom,axis:[1,0,0],travel:3,latching:true,meta:{mechanism:'slide',electricalBehavior:false,surfaceCenter:[7.5,-27.02,-2.5],surfaceFace:'bottom'}});
  const z=-15.77;for(const x of [-21,21])for(const y of [-21,21])screw(this.body,[x,y,z],'back',1.5);
  for(const x of [-12,12]){const insert=new THREE.Shape();insert.absarc(0,0,2,0,Math.PI*2,false);const hole=new THREE.Path();hole.absarc(0,0,1.15,0,Math.PI*2,true);insert.holes.push(hole);const m=mesh(this.body,new THREE.ExtrudeGeometry(insert,{depth:2,bevelEnabled:false,curveSegments:40}),materials.metal(0xb6a15f,{roughness:.4}),[x,0,z]);m.name='DinBase threaded insert';}
 }
}
