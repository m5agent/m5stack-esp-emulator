import * as THREE from 'three';
import {Component,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,portQuaternion,screw} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';

function circularHole(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(h);}
function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:40}),material,position,name);}
function rectangle(w,h){const s=new THREE.Shape();s.moveTo(-w/2,-h/2);s.lineTo(-w/2,h/2);s.lineTo(w/2,h/2);s.lineTo(w/2,-h/2);s.closePath();return s;}
function cylinder(parent,r,depth,position,material,name){return mesh(parent,new THREE.CylinderGeometry(r,r,depth,48).rotateX(Math.PI/2),material,position,name);}

function board(host){
 // Open contours clear the two native mounting bosses and the Grove body.
 // This clockwise exterior uses explicitly counter-clockwise bore paths.
 const s=new THREE.Shape();
 s.moveTo(-6.4,13.8);s.lineTo(6.4,13.8);s.lineTo(10.4,9.8);s.lineTo(10.4,.35);s.lineTo(8,.35);
 s.absarc(8,-4,4.35,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.4,-8.35);s.lineTo(10.4,-9.8);s.lineTo(6.4,-13.8);
 s.lineTo(5.6,-13.8);s.lineTo(5.6,-8.5);s.lineTo(-5.6,-8.5);s.lineTo(-5.6,-13.8);s.lineTo(-6.4,-13.8);
 s.lineTo(-10.4,-9.8);s.lineTo(-10.4,-8.35);s.lineTo(-8,-8.35);s.absarc(-8,-4,4.35,Math.PI*1.5,Math.PI*2.5,false);
 s.lineTo(-10.4,.35);s.lineTo(-10.4,9.8);s.closePath();circularHole(s,0,-4,2.1);
 for(const x of [-3,-1,1,3])circularHole(s,x,-8.1,.32);
 const pcb=solid(host.body,s,.8,[0,0,-.3],materials.plastic(0x274a3c,{roughness:.9}),'ToF4M PCB with open boss and Grove relief');
 pcb.userData={role:'physical-pcb',scope:'Reconstructed visible board and concealed support; no trace-level or electrical model'};
 return pcb;
}

function opticalPackage(host){
 // ST optical LGA12 envelope, 4.9 × 2.5 × 1.56 mm. The package is
 // volumetric; separate filter panes have real lens/emitter bodies beneath.
 const group=new THREE.Group();group.name='ToF4M VL53L1CXV0FY/1 physical optical package';group.position.set(0,8,.5);host.body.add(group);
 const dark=materials.plastic(0x252a25,{roughness:.7}),gold=materials.glossy(0xa4a24b,{roughness:.42});
 const substrate=mesh(group,new THREE.BoxGeometry(4.8,2.4,.2),materials.plastic(0x34452e,{roughness:.9}),[0,0,.1],'VL53L1X LGA12 substrate');
 const profile=rectangle(4.9,2.5);
 for(const x of [-1.48,1.52]){const h=new THREE.Path();h.moveTo(x-.81,-.94);h.lineTo(x+.81,-.94);h.lineTo(x+.81,.94);h.lineTo(x-.81,.94);h.closePath();profile.holes.push(h);}
 const enclosure=solid(group,profile,1.36,[0,0,.2],dark,'VL53L1X molded optical enclosure with two real filter wells');
 const receiverFloor=mesh(group,new THREE.BoxGeometry(1.62,1.88,.8),dark,[-1.48,0,.6],'VL53L1X receiver well floor');
 const emitterFloor=mesh(group,new THREE.BoxGeometry(1.62,1.88,.8),dark,[1.52,0,.6],'VL53L1X emitter well floor');
 const lens=cylinder(group,.425,.22,[-1.48,0,1.11],materials.glossy(0x283b25,{roughness:.16}),'VL53L1X recessed SPAD receiver lens');
 const emitter=cylinder(group,.35,.16,[1.52,0,1.08],materials.glossy(0x514e2b,{roughness:.27}),'VL53L1X passive 940nm VCSEL emitter');
 const filters=[];for(const x of [-1.48,1.52])filters.push(mesh(group,new THREE.BoxGeometry(1.62,1.88,.10),gold,[x,0,1.41],'VL53L1X solid infrared filter glass'));
 // Photo-derived muted olive filter color does not emit light. No IR LED
 // component or ranging/scan animation is exposed by this appearance model.
 const pads=[];for(const side of [-1,1])for(let i=0;i<6;i++)pads.push(mesh(group,new THREE.BoxGeometry(.5,.2,.06),materials.metal(0xa69b71,{roughness:.5}),[-2+i*.8,side*1.1,.03],'VL53L1X LGA edge contact'));
 group.userData={role:'physical-sensor-package',part:'VL53L1CXV0FY/1',envelopeMm:[4.9,2.5,1.56],scope:'Passive solid package and optics only; no IR light, distance, scan, measurement, laser propagation, I2C or electrical simulation',inferred:spec.source.inferred};
 return {group,substrate,enclosure,receiverFloor,emitterFloor,lens,emitter,filters,pads};
}
function supportParts(host){
 const parts=[],black=materials.plastic(0x242821,{roughness:.85}),ceramic=materials.plastic(0xa6956f,{roughness:.9}),metal=materials.metal(0xa5a494,{roughness:.6});
 parts.push(mesh(host.body,new THREE.BoxGeometry(2.8,1.3,.8),black,[0,3,.9],'ToF4M HT7533 regulator package'));
 for(const[x,y]of[[-5.5,6],[-5.5,3],[5.5,6],[5.5,3]]){parts.push(mesh(host.body,new THREE.BoxGeometry(1.1,.65,.45),black,[x,y,.725],'ToF4M pull-up resistor package'));for(const d of[-.45,.45])parts.push(mesh(host.body,new THREE.BoxGeometry(.2,.65,.46),metal,[x+d,y,.73],'ToF4M resistor termination'));}
 for(const[x,y]of[[-4,11],[4,11],[-2,2],[2,2]])parts.push(mesh(host.body,new THREE.BoxGeometry(1.5,.8,.5),ceramic,[x,y,.75],'ToF4M decoupling capacitor package'));
 return parts;
}

export function buildToF4M(host){
 addCadParts(host,data,{shell:materials.plastic(0xe4e6df,{roughness:.8})});
 const pcb=board(host),optics=opticalPackage(host),support=supportParts(host);
 const socket=connector(host.body,32,false,{height:5.2});socket.name='ToF4M red open-top HY2.0-4P';socket.children[0].material.color.setHex(spec.grove.color);
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],
  pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],
  meta:{role:'visual-connector',face:'bottom',protocol:'I2C',scope:'Physical connector, attachment and cable pose only; no bus or electrical behavior'}}));
 screw(host.body,[0,-4,-3.97],'back',1.4);
 const shank=cylinder(host.body,.65,1.6,[0,-4,-2.65],materials.metal(0x919997,{roughness:.5}),'ToF4M concealed mounting screw shank');
 host.add(new Component({id:'sensor',label:'VL53L1CXV0FY/1 appearance anchor',position:[0,8,2.06],meta:{role:'visual-anchor',part:'VL53L1CXV0FY/1',scope:'No commands, distance, IR emission, scan, laser propagation, sensor values, I2C or electrical behavior'}}));
 addStickers(host);
 host.tof4mAssembly={pcb,optics,support,socket,port,shank};
}
