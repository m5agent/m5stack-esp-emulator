import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {mesh,slab,grove,FACE} from '../../modeling/parts.js';
import {cadButton} from '../../modeling/actuators.js';
import {usbC,microSD} from '../../modeling/connectors.js';

function mainBoard(host){
 // The photo-visible PCB follows the enclosure; edge reliefs clear the Grove,
 // power plunger and 0928 speaker instead of crossing those physical packages.
 const shape=new THREE.Shape();
 const outline=[[-24.5,-24.5],[24.5,-24.5],[24.5,-10],[21.4,-10],[21.4,20.4],[24.5,20.4],[24.5,24.5],[-24.5,24.5],[-24.5,18.5],[-22.8,18.5],[-22.8,7.5],[-24.5,7.5],[-24.5,-8.5],[-20.8,-8.5],[-20.8,-19.5],[-24.5,-19.5]];
 outline.forEach(([x,y],i)=>i?shape.lineTo(x,y):shape.moveTo(x,y));shape.closePath();
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(shape,{depth:.8,bevelEnabled:false}),materials.plastic(0x22352b,{roughness:.92}),[0,0,-3.1],'Core2 main PCB');pcb.userData.dimensionSource='Photo-derived board extent; package reliefs follow the official shell openings';
 const solder=materials.metal(0xaeb6a6,{roughness:.5});
 for(const y of [-17,-15,-13,-11]){
  mesh(host.body,new THREE.BoxGeometry(1.8,.45,.45),solder,[-21.2,y,-1.15],'Core2 Grove contact elbow');
  mesh(host.body,new THREE.BoxGeometry(.45,.45,2.4),solder,[-20.55,y,-2.35],'Core2 Grove PCB contact tail');
 }
 for(const x of [-12.6,-.4])mesh(host.body,new THREE.BoxGeometry(.6,2.4,2.6),solder,[x,-23.8,-1.1],'Core2 microSD shield mount');
 for(const y of [-3.6,3.6])mesh(host.body,new THREE.BoxGeometry(2.8,.7,1.25),solder,[-22.5,y,-2.05],'Core2 USB shield solder mount');
 // LCD module and carrier sit behind the existing front glass/framebuffer.
 slab(host.body,48.8,44.8,.8,1.2,[0,2,5.55],materials.plastic(0x202824,{roughness:.88}),[],.06).name='Core2 display carrier';
 slab(host.body,44.3,35.7,1.7,.5,[0,2,6.35],materials.metal(0x777d77,{roughness:.65}),[],.04).name='Core2 LCD module back';
}

function speaker(host){
 const group=new THREE.Group();group.name='Core2 0928 speaker';group.position.set(25.2,5,0);group.quaternion.copy(FACE.right);host.body.add(group);
 slab(group,28,9,2.5,4.45,[0,0,-3.05],materials.plastic(0x222726,{roughness:.88}),[],.06).name='Core2 speaker enclosure';
 const rim=roundedRect(27.4,8.4,4.1);rim.holes.push(roundedRect(25.7,6.7,3.2,{path:new THREE.Path(),clockwise:true}));
 mesh(group,new THREE.ExtrudeGeometry(rim,{depth:.24,bevelEnabled:false,curveSegments:32}),materials.metal(0x515853,{roughness:.7}),[0,0,-.12],'Core2 speaker frame');
 slab(group,25.7,6.7,.2,3.25,[0,0,-.3],materials.plastic(0x151b18,{roughness:1}),[],.025).name='Core2 recessed speaker diaphragm';
}

function controls(host){
 // Separate the visible integral CAD key faces from the fixed molding; keep
 // their native travel slots and the actual recessed switch bodies behind them.
 cadButton(host,{source:host.parts['upper-housing'],id:'power',label:'Power',position:[-27,13,-.75],face:'left',w:6.4,h:7.5,r:3.1,depth:1.25,travel:.18});
 const power=new THREE.Group();power.name='Core2 power key backing';power.position.set(-25.25,13,-.75);power.quaternion.copy(FACE.left);host.body.add(power);
 slab(power,10,10,1.6,4.7,[0,0,-1.6],materials.plastic(0x252d26,{roughness:.9}),[],.04).name='Core2 power switch housing';
 cadButton(host,{source:host.parts['upper-housing'],id:'reset',label:'RST',position:[14.5,-27,.75],face:'bottom',w:7.3,h:5.4,r:1.4,depth:1.25,travel:.18});
 const reset=new THREE.Group();reset.name='Core2 reset switch backing';reset.position.set(14.5,-25.25,.75);reset.quaternion.copy(FACE.bottom);host.body.add(reset);
 slab(reset,8.6,7.3,2.3,3.2,[0,0,-2.3],materials.plastic(0x272e27,{roughness:.9}),[],.05).name='Core2 reset switch housing';
 // The small status/microphone holes remain open, with their physical packages behind them.
 mesh(host.body,new THREE.BoxGeometry(3.5,2.4,2.7),materials.plastic(0x242d26,{roughness:.9}),[7,-24.3,-.05],'Core2 microphone/status package');
 mesh(host.body,new THREE.BoxGeometry(4.4,2.5,2.8),materials.plastic(0x29302b,{roughness:.9}),[6.5,-24,-3.1],'Core2 lower port packages');
}

export function core2Assembly(host){
 mainBoard(host);speaker(host);
 usbC(host,{position:[-27.02,0,0],face:'left',w:8.7,h:3.1,depth:5});
 const connector=grove(host,{position:[-27.02,-14,-1],face:'left',w:9.8,h:5,color:0xa62532});connector.name='Core2 Grove socket';
 microSD(host,{position:[-6.5,-27.02,.75],face:'bottom',w:13,h:1.5,depth:5});
 controls(host);
}
