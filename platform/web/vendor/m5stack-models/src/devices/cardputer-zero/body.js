import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {slab,mesh,disc,FACE,screw} from '../../modeling/parts.js';
import {DIM} from './dimensions.js';

export function addBody(host,keyCenters){
 const dark=materials.plastic(0x424849,{roughness:.8}),white=materials.plastic(0xcdd1cc,{roughness:.8});
 const backHoles=[];
 for(const x of [-36,-20,20,36])backHoles.push({w:5.4,h:5.4,r:2.7,cx:x,cy:23});
 for(const x of [-27.4,27.4])backHoles.push({w:3.9,h:3.9,r:1.95,cx:x,cy:23});
 for(const x of [-14.1,14.1])backHoles.push({w:3.4,h:3.4,r:1.7,cx:x,cy:23});
 for(const x of [-8.3,8.3])backHoles.push({w:6.1,h:3.8,r:.8,cx:x,cy:23});
 backHoles.push({w:7.3,h:7.3,r:3.65,cx:0,cy:20.8});
 slab(host.body,84,54,1.4,2.6,[0,0,DIM.shell.back],dark,backHoles,.18).name='Rear battery enclosure cover';
 // The flat rear is the fixed enclosure cover visible in gallery-08. There is
 // no evidence of a separate rectangular battery door or removable battery.
 const darkCenter=(DIM.shell.back+1.4+DIM.shell.split)/2,darkHeight=DIM.shell.split-(DIM.shell.back+1.4);
 const whiteCenter=(DIM.shell.split+DIM.shell.front)/2,whiteHeight=DIM.shell.front-DIM.shell.split;
 const p=DIM.ports;
 const sideSpecs=[
  {face:'right',x:40.4,holes:[
   {w:14.8,h:5.8,r:.35,cx:p.hdmi[1],z:p.hdmi[2]},
   {w:5.5,h:5.5,r:2.75,cx:p.audio[1],z:p.audio[2]},
   {w:10.5,h:5.8,r:.3,cx:p.grove[1],z:p.grove[2]}
  ]},
  {face:'left',x:-40.4,holes:[
   {w:13.8,h:6.5,r:.3,cx:-p.usbA[1],z:p.usbA[2]},
   {w:16.6,h:13.8,r:.35,cx:-p.ethernet[1],z:p.ethernet[2]}
  ]}
 ];
 for(const s of sideSpecs){
  const panel=slab(host.body,50.4,darkHeight,1.6,.25,[s.x,0,darkCenter],dark,s.holes.map(h=>({...h,cy:h.z-darkCenter})),.06);panel.quaternion.copy(FACE[s.face]);panel.name=`${s.face} lower shell`;
  const top=slab(host.body,50.4,whiteHeight,1.6,.25,[s.x,0,whiteCenter],white,[{w:9.3,h:3.4,r:1.45,cx:s.face==='left'?-13.1:13.1,cy:6.65-whiteCenter}],.05);top.quaternion.copy(FACE[s.face]);top.name=`${s.face} white lid edge`;
 }
 const topHoles=[{w:19,h:6.2,r:.25,cx:0,cy:-(1.2-darkCenter)},...[-27.5,27.5].map(cx=>({w:4.2,h:9.8,r:.4,cx,cy:-(-5-darkCenter)})),...[-8,8].map(cx=>({w:5,h:5,r:2.5,cx,cy:-(-7.5-darkCenter)}))];
 for(const x of [-21,-18,-15,-12,12,15,18,21])topHoles.push({w:.7,h:2.8,r:.3,cx:x,cy:-(-2.7-darkCenter)});
 const top=slab(host.body,79,darkHeight,1.6,.25,[0,25.4,darkCenter],dark,topHoles,.06);top.quaternion.copy(FACE.top);top.name='Upper expansion shell';
 const lowerHoles=Array.from({length:8},(_,i)=>({w:.8,h:4.1,r:.35,cx:(i-3.5)*3,cy:1-darkCenter}));
 lowerHoles.push({w:16,h:2,r:.3,cx:0,cy:-8-darkCenter});
 const bottom=slab(host.body,79,darkHeight,1.6,.25,[0,-25.4,darkCenter],dark,lowerHoles,.06);bottom.quaternion.copy(FACE.bottom);bottom.name='Lower speaker shell';
 const topWhite=slab(host.body,79,whiteHeight,1.6,.25,[0,25.4,whiteCenter],white,[{w:12.8,h:2.1,r:.2,cx:-18.1,cy:-(6-whiteCenter)},{w:5.8,h:2.4,r:.25,cx:-30.4,cy:-(6.2-whiteCenter)},{w:1.3,h:1.8,r:.5,cx:34.5,cy:-(6.1-whiteCenter)}],.05);topWhite.quaternion.copy(FACE.top);topWhite.name='Upper white lid edge';
 const bottomWhite=slab(host.body,79,whiteHeight,1.6,.25,[0,-25.4,whiteCenter],white,[],.05);bottomWhite.quaternion.copy(FACE.bottom);bottomWhite.name='Lower white lid edge';
 for(const x of [-39.4,39.4])for(const y of [-24.4,24.4]){
  mesh(host.body,new THREE.CylinderGeometry(2.6,2.6,darkHeight,24).rotateX(Math.PI/2),dark,[x,y,darkCenter],'Lower shell rounded corner');
  mesh(host.body,new THREE.CylinderGeometry(2.6,2.6,whiteHeight,24).rotateX(Math.PI/2),white,[x,y,whiteCenter],'White lid rounded corner');
 }
 const deckHoles=keyCenters.map(({x,y})=>({w:5.7,h:3.35,r:1.45,cx:x,cy:y}));
 deckHoles.push({w:44.8,h:24.8,r:.65,cx:.8,cy:13.1},{w:.8,h:2.8,r:.35,cx:-33.1,cy:2.55});
 slab(host.body,84,54,1.4,2.6,[0,0,DIM.shell.deckBase],white,deckHoles,.1).name='Drilled 46-key front lid';
 slab(host.body,45.5,25.4,2.8,.7,[.8,13.1,7.3],materials.plastic(0x111817,{roughness:.74}),[],.12).name='LCD module and bezel';
 for(const x of [-24.2,24.4])slab(host.body,1.7,24.7,1.75,.6,[x,13.1,9.8],white,[],.3).name='Raised display side guard';
 for(const x of [-40,40])slab(host.body,1.7,7.3,1.75,.5,[x,22.5,9.8],white,[],.3).name='Raised corner guard';
 for(const [x,y]of [[-29,3.2],[28,12.3]])screw(host.body,[x,y,9.88],'front',1.55);
 const mic=slab(host.body,1.8,3.6,.6,.25,[-33.1,2.55,7.7],materials.plastic(0x171e1a),[],.05);mic.name='Microphone recess backing';
 // Real internal solids back the assembled shells and vents; sizes are inferred.
 slab(host.body,54,39,6,.8,[7,-2,-10.0],materials.metal(0xa9ada8,{roughness:.83}),[],.15).name='1750 mAh battery body';
 const pcbShape=new THREE.Shape();pcbShape.moveTo(-27.4,-24);pcbShape.lineTo(39.2,-24);pcbShape.lineTo(39.2,24);pcbShape.lineTo(-39.2,24);pcbShape.lineTo(-39.2,-4.5);pcbShape.lineTo(-27.4,-4.5);pcbShape.closePath();
 mesh(host.body,new THREE.ExtrudeGeometry(pcbShape,{depth:1,bevelEnabled:false}),materials.plastic(0x284333,{roughness:.9}),[0,0,-4.1],'Main PCB with Ethernet clearance');
 const speaker=slab(host.body,24,6.4,1.3,2,[0,-24.2,1],materials.plastic(0x171f1c,{roughness:.95}),[],.12);speaker.quaternion.copy(FACE.bottom);speaker.name='Speaker acoustic enclosure';
 const grip=slab(host.body,17,3,1,.35,[0,-24.4,-8],dark,[],.08);grip.quaternion.copy(FACE.bottom);grip.name='Lower blind grip pocket';
 for(const x of [-27.5,27.5]){const o=slab(host.body,4.5,10.1,.8,.4,[x,24.4,-5],dark,[],.08);o.quaternion.copy(FACE.top);o.name='Upper blind grip pocket';}
 for(const x of [-8,8]){const o=disc(host.body,2.5,[x,23.8,-7.5],materials.plastic(0x171f1c));o.quaternion.copy(FACE.top);o.name='Top mounting blind-hole floor';}
 for(const x of [-36,-20,20,36]){
  const shape=new THREE.Shape();shape.absarc(0,0,3.3,0,Math.PI*2);const hole=new THREE.Path();hole.absarc(0,0,2.7,0,Math.PI*2,true);shape.holes.push(hole);
  mesh(host.body,new THREE.ExtrudeGeometry(shape,{depth:6.3,bevelEnabled:false,curveSegments:32}),dark,[x,23,-11.55],'Rear LEGO-compatible mounting tube');
  const o=disc(host.body,2.7,[x,23,-5.2],materials.plastic(0x151d19));o.quaternion.copy(FACE.back);o.name='Rear mounting blind-hole floor';
 }
 for(const x of [-27.4,27.4])screw(host.body,[x,23,-10.85],'back',1.65);
 for(const x of [-14.1,14.1]){
  const brass=new THREE.Group();brass.position.set(x,23,-11.51);brass.quaternion.copy(FACE.back);host.body.add(brass);brass.name='Rear brass mounting insert';
  slab(brass,3.2,3.2,.6,1.55,[0,0,-.5],materials.metal(0xa58c39,{roughness:.46}),[{w:1.45,h:1.45,r:.72}],.035);
  mesh(brass,new THREE.CircleGeometry(.72,32),materials.plastic(0x171d18),[0,0,-.55],'Threaded insert blind floor');
 }
 for(const x of [-8.3,8.3]){const o=slab(host.body,6.1,3.8,.25,.8,[x,23,-10.5],materials.plastic(0x202824),[],.04);o.quaternion.copy(FACE.back);o.name='Rear CAP retention pocket';}
 const camera=new THREE.Group();camera.position.set(0,20.8,-11.5);camera.quaternion.copy(FACE.back);host.body.add(camera);camera.name='IMX219 camera assembly';
 const barrel=new THREE.Shape();barrel.absarc(0,0,3.45,0,Math.PI*2);const barrelBore=new THREE.Path();barrelBore.absarc(0,0,1.9,0,Math.PI*2,true);barrel.holes.push(barrelBore);
 mesh(camera,new THREE.ExtrudeGeometry(barrel,{depth:1.6,bevelEnabled:false,curveSegments:48}),materials.plastic(0x1e2520,{roughness:.72}),[0,0,-1.3],'Camera lens barrel');
 const bezel=new THREE.Shape();bezel.absarc(0,0,3.1,0,Math.PI*2);const lensHole=new THREE.Path();lensHole.absarc(0,0,1.8,0,Math.PI*2,true);bezel.holes.push(lensHole);
 mesh(camera,new THREE.ExtrudeGeometry(bezel,{depth:.25,bevelEnabled:false,curveSegments:48}),materials.plastic(0x111a15),[0,0,.15],'Camera aperture bezel');
 mesh(camera,new THREE.CircleGeometry(1.8,48),materials.glossy(0x143b32,{roughness:.08,clearcoat:.5}),[0,0,.11],'Camera optical glass');
 return {white,dark};
}
