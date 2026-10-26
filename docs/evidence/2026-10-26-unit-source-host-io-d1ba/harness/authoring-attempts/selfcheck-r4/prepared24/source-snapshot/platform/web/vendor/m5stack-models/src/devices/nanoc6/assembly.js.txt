import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {mesh,slab,grove,FACE} from '../../modeling/parts.js';
import {usbC} from '../../modeling/connectors.js';
import {DIM} from './dimensions.js';

export function nanoAssembly(host){
 // The board edge and its underside packages are visible through the official
 // rear/end slots. Keep those real slots, and put the assembly behind them.
 slab(host.body,11.3,22.6,.6,.45,[0,0,-1],materials.plastic(0x30513c,{roughness:.88}),[],.025).name='NanoC6 main PCB';
 const gold=materials.metal(0xa69851,{roughness:.6});
 for(const x of [-5.66,5.66])mesh(host.body,new THREE.BoxGeometry(.13,7.5,.48),gold,[x,7.25,-.68],'NanoC6 plated board edge');
 usbC(host,{...DIM.usb,face:'bottom',depth:3.5});
 const connector=grove(host,{...DIM.grove,face:'top',w:10,h:4.3,depth:5.8});connector.name='NanoC6 Grove socket';
 const solder=materials.metal(0xabb3a4,{roughness:.48}),white=materials.plastic(0xd3d8cb,{roughness:.8});
 for(const x of [-3,-1,1,3]){
  mesh(host.body,new THREE.BoxGeometry(.42,1.1,.42),solder,[x,6.15,2.05],'NanoC6 Grove contact elbow');
  mesh(host.body,new THREE.BoxGeometry(.42,.42,2.85),solder,[x,5.8,.85],'NanoC6 Grove PCB tail');
 }
 for(const x of [-4.35,4.35])mesh(host.body,new THREE.BoxGeometry(.55,2.4,.45),solder,[x,-9.55,-.42],'NanoC6 USB shield solder tab');
 // Photo-visible white underside strips and packages: model their thickness,
 // leaving a recessed view through every rear slot rather than closing the shell.
 slab(host.body,8.4,2,1.35,.2,[0,8.9,-2.35],white,[],.04).name='NanoC6 Grove underside molding';
 slab(host.body,7.4,2.5,1.45,.2,[0,-8.3,-2.45],white,[],.04).name='NanoC6 USB-side ceramic package';
 slab(host.body,4.8,4.8,.95,.12,[0,-2.7,-1.95],materials.plastic(0x282e29,{roughness:.9}),[],.025).name='NanoC6 rear IC package';
 for(const x of [-3.1,3.1])for(const y of [-6.1,-3.6,0])mesh(host.body,new THREE.BoxGeometry(.85,1.2,.6),materials.plastic(0x333a31,{roughness:.88}),[x,y,-1.3],'NanoC6 rear passive package');
 const rgb=new THREE.Group();rgb.name='NanoC6 RGB package';rgb.position.set(-5.55,4.85,-1.55);rgb.quaternion.copy(FACE.left);host.body.add(rgb);
 slab(rgb,1.7,1.1,.7,.08,[0,0,-.7],white,[],.025).name='NanoC6 RGB board package';
}
