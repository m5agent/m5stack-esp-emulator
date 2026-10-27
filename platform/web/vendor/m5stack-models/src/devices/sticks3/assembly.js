import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {FACE,mesh,slab,header} from '../../modeling/parts.js';

function insertRing(parent,outer,inner,depth,z,name){
 const shape=new THREE.Shape();shape.absarc(0,0,outer,0,Math.PI*2,false);const hole=new THREE.Path();hole.absarc(0,0,inner,0,Math.PI*2,true);shape.holes.push(hole);
 return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:40}),materials.metal(0xbba15d,{roughness:.43}),[0,0,z],name);
}

/** Appearance inserts omitted from the official molded-shell assembly. */
export function addAssembly(host){
 const dark=materials.plastic(0x15191b,{roughness:.88}),board=materials.plastic(0x24443c,{roughness:.92});
 slab(host.body,17.1,27.1,1.9,.7,[0,6.1,4.55],dark,[],.08).name='LCD module with physical depth';
 slab(host.body,20.2,39.85,.8,1.0,[0,.125,-1.1],board,[],.04).name='StickS3 main PCB';
 slab(host.body,17.8,27.5,3.3,1.0,[0,0,-6.7],materials.plastic(0x757b7a,{roughness:.65}),[],.12).name='Internal battery envelope';
 // A real rectangular package occupies the corner clearance around the USB capsule.
 // Its lower PCB edge also clears this package and the two assembly screw shafts.
 const usbPackage=new THREE.Group();usbPackage.position.set(0,-23.8,1.6);usbPackage.quaternion.copy(FACE.bottom);usbPackage.name='USB-C package surround';host.body.add(usbPackage);
 slab(usbPackage,10.2,4.2,3.5,.45,[0,0,-3.5],dark,[{w:8.9,h:3.2,r:1.6}],.035).name='USB-C rectangular package surround';
 // The Hat2 mouth is a real 2×8 array; no painted connector face is used.
 const hat=header(host.body,{position:[0,23.8,-4.15],face:'top',cols:8,rows:2});hat.name='Hat2 physical 2x8 receptacle';
 const carrier=new THREE.Group();carrier.position.set(0,20.7,-2.4);carrier.quaternion.copy(FACE.top);carrier.name='Top I/O daughterboard';host.body.add(carrier);
 slab(carrier,20.5,7.2,.8,.55,[0,0,0],board,[],.035).name='Hat2 and IR carrier PCB';
 for(let c=0;c<8;c++)for(const z of [-5.42,-2.88])mesh(host.body,new THREE.BoxGeometry(.4,.8,.4),materials.metal(0xb2a77c),[(c-3.5)*2.54,21.72,z],'Hat2 solder tail');
 // Original shell slots are at X −2/0/+2, Z −1.2…+0.7, not on the upper solid wall.
 mesh(host.body,new THREE.BoxGeometry(8.4,1.8,2.2),dark,[0,22.55,-.25],'Speaker acoustic enclosure');
 const tx=new THREE.Group();tx.position.set(6.5,23.1,-1.2);tx.quaternion.copy(FACE.top);tx.name='IR transmitter package';host.body.add(tx);
 slab(tx,3.4,1.8,2,.3,[0,0,-2],dark,[],.04).name='IR transmitter dielectric base';
 const rx=new THREE.Group();rx.position.set(-6.3,23.75,-1.2);rx.quaternion.copy(FACE.top);rx.name='IR receiver package';host.body.add(rx);
 slab(rx,3.1,1.8,2.1,.25,[0,0,-2.1],materials.glossy(0x080d0e,{roughness:.2}),[],.04).name='IR receiver optical window';
 // Physical carriers sit behind the integral molded side keys, with a gap to
 // the main PCB. Otherwise their travel slots expose the unrelated blue KEY1 stem.
 mesh(host.body,new THREE.BoxGeometry(1.1,10.2,8.5),dark,[10.85,0,1],'KEY2 switch carrier');
 mesh(host.body,new THREE.BoxGeometry(1.1,6.5,8.5),dark,[-10.85,-15.7,1],'Power switch carrier');
 // Mechanical drawing: rear M2 inserts are 18 mm apart and 8.5 mm from the bottom.
 // The selected CAD's small source-origin offset is retained in these centers.
 for(const x of [-9,9]){
  const insert=new THREE.Group();insert.position.set(x,-15.56,-7.52);insert.quaternion.copy(FACE.back);insert.name='Rear M2 brass insert';host.body.add(insert);
  insertRing(insert,.99,.8,2.7,-2.7,'M2 insert barrel');insertRing(insert,1.25,.8,.12,-.12,'M2 insert flange');
  mesh(insert,new THREE.CircleGeometry(.81,40),dark,[0,0,-2.8],'M2 blind bore floor');
  const screw=new THREE.Group();screw.position.set(x,-21.06,-3.45);screw.quaternion.copy(FACE.back);screw.name='Recessed lower assembly screw';host.body.add(screw);
  const head=new THREE.Shape();head.absarc(0,0,1.35,0,Math.PI*2,false);const hex=new THREE.Path();
  for(let i=0;i<6;i++){const a=-i*Math.PI/3;if(i)hex.lineTo(.55*Math.cos(a),.55*Math.sin(a));else hex.moveTo(.55,0);}hex.closePath();head.holes.push(hex);
  mesh(screw,new THREE.ExtrudeGeometry(head,{depth:1.05,bevelEnabled:false,curveSegments:32}),materials.metal(0x7d8686,{roughness:.43}),[0,0,-1.05],'Screw head with real hex recess');
  mesh(screw,new THREE.CircleGeometry(.57,6),dark,[0,0,-.7],'Screw hex floor');
  mesh(screw,new THREE.CylinderGeometry(.8,.8,4,24).rotateX(Math.PI/2),materials.metal(0x717b7c),[0,0,-3],'Screw shaft');
 }

}
