import * as THREE from 'three';
import {Component,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,portQuaternion} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';
function bore(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(h);}
function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:48}),material,position,name);}
function boardShape(){
 // Circular mounting-boss reliefs intersect the top/bottom perimeter, so they
 // belong to the exterior contour rather than invalid intersecting holes.
 const s=new THREE.Shape(),r=4.7,top=22,bottom=-25,xt=Math.sqrt(r*r-4),xb=Math.sqrt(r*r-1);
 s.moveTo(-16+xt,top);s.lineTo(16-xt,top);s.absarc(16,24,r,Math.atan2(-2,-xt),Math.atan2(-2,xt),false);s.lineTo(22.2,top);s.lineTo(22.2,bottom);s.lineTo(16+xb,bottom);
 s.absarc(16,-24,r,Math.atan2(-1,xb),Math.atan2(-1,-xb)+Math.PI*2,false);s.lineTo(5.6,bottom);s.lineTo(5.6,-21.4);s.lineTo(-5.6,-21.4);s.lineTo(-5.6,bottom);s.lineTo(-16+xb,bottom);
 s.absarc(-16,-24,r,Math.atan2(-1,xb),Math.atan2(-1,-xb)+Math.PI*2,false);s.lineTo(-22.2,bottom);s.lineTo(-22.2,top);s.lineTo(-16-xt,top);s.absarc(-16,24,r,Math.atan2(-2,-xt),Math.atan2(-2,xt),false);s.closePath();
 for(const x of[-3,-1,1,3])bore(s,x,-20.85,.32);for(const x of[-5.08,-2.54,0,2.54,5.08])bore(s,x,-14.3,.38);return s;
}
function boards(host){
 const green=materials.plastic(0x1b5c41,{roughness:.91}),metal=materials.metal(0xc1b990,{roughness:.49});
 const carrier=solid(host.body,boardShape(),.8,[0,0,-3.8],green,'UHF RFID physical carrier PCB with open mounting relief and true solder bores');carrier.userData={role:'physical-pcb',inferred:true,scope:'Concealed visual reconstruction; outline/stack/placement constrained by native shell, no production board drawing'};
 const shape=new THREE.Shape();shape.moveTo(-19,-15.5);shape.lineTo(19,-15.5);shape.lineTo(19,19.5);shape.lineTo(-19,19.5);shape.closePath();for(const x of[-5.08,-2.54,0,2.54,5.08])bore(shape,x,-14.3,.38);
 const module=solid(host.body,shape,.8,[0,0,-1.7],green,'JRD-4035 physical module PCB with true five-pin interface bores');module.userData={role:'physical-module-pcb',part:'JRD-4035',inferred:true,scope:'Integrated module existence confirmed; board profile, size and plane inferred'};
 const pads=[];for(const[x,y,r]of[...[-3,-1,1,3].map(x=>[x,-20.85,.32]),...[-5.08,-2.54,0,2.54,5.08].map(x=>[x,-14.3,.38])]){const s=new THREE.Shape();s.absarc(x,y,r+.3,0,Math.PI*2,false);bore(s,x,y,r);pads.push(solid(host.body,s,.04,[0,0,-3.84],metal,'UHF RFID carrier solder annulus'));}
 return{carrier,module,pads};
}
function moduleAssembly(host){
 const group=new THREE.Group();group.name='JRD-4035 concealed physical module and ceramic patch';host.body.add(group);
 const silver=materials.metal(0xbfc3b9,{roughness:.52}),ceramic=materials.plastic(0xe3ded0,{roughness:.86}),dark=materials.plastic(0x292d29,{roughness:.87}),gold=materials.metal(0xb8a760,{roughness:.43});
 // No public module mechanical drawing exists. These unmarked fixed solids
 // show the confirmed physical assembly without inventing RF circuitry.
 const shield=new THREE.Group();shield.name='UHF RFID inferred concealed RF shield';group.add(shield);
 mesh(shield,new THREE.BoxGeometry(18,19,.15),silver,[0,2,-2.875],'UHF RFID inferred RF shield back lid');
 for(const x of[-8.925,8.925])mesh(shield,new THREE.BoxGeometry(.15,19,1.05),silver,[x,2,-2.275],'UHF RFID RF shield side wall');for(const y of[-7.425,11.425])mesh(shield,new THREE.BoxGeometry(17.7,.15,1.05),silver,[0,y,-2.275],'UHF RFID RF shield end wall');
 shield.userData={role:'physical-shield',inferred:true,scope:'Unmarked concealed shield envelope only; not an asserted module internal schematic or production package'};
 const ground=mesh(group,new THREE.BoxGeometry(25.5,25.5,.07),silver,[0,2,-.865],'UHF RFID ceramic patch ground electrode');
 const body=mesh(group,new THREE.BoxGeometry(25,25,4.1),ceramic,[0,2,1.22],'UHF RFID solid ceramic antenna dielectric');body.userData={role:'physical-ceramic-antenna',inferred:true,scope:'Integrated ceramic antenna confirmed; 25 mm envelope and installed geometry inferred, no RF field or read simulation'};
 const shape=new THREE.Shape();shape.moveTo(-11.2,-11.2);shape.lineTo(9.5,-11.2);shape.lineTo(11.2,-9.5);shape.lineTo(11.2,11.2);shape.lineTo(-9.5,11.2);shape.lineTo(-11.2,9.5);shape.closePath();
 const electrode=solid(group,shape,.035,[0,2,3.272],silver,'UHF RFID ceramic patch top metallization with inferred corner relief');
 const feed=mesh(group,new THREE.CylinderGeometry(.25,.25,5,32).rotateX(Math.PI/2),gold,[3.5,2,.8],'UHF RFID inferred ceramic patch feedthrough pin');
 const feedPad=mesh(group,new THREE.CylinderGeometry(.65,.65,.06,40).rotateX(Math.PI/2),gold,[3.5,2,3.315],'UHF RFID ceramic patch feed pad');
 const header=mesh(group,new THREE.BoxGeometry(14,1.9,1.1),dark,[0,-14.3,-2.35],'UHF RFID internal P1 five-pin insulating spacer');
 const headerPins=[];for(const x of[-5.08,-2.54,0,2.54,5.08])headerPins.push(mesh(group,new THREE.BoxGeometry(.5,.5,3.2),gold,[x,-14.3,-2.3],'UHF RFID internal P1 metal pin'));
 group.userData={role:'physical-rf-module',part:'JRD-4035',inferred:true,scope:'Fixed visual package, antenna and five-pin assembly; no chip identities, RF topology, UART, tags, scan, field, EPC or protocol behavior'};
 return{group,shield,ground,body,electrode,feed,feedPad,header,headerPins};
}
function interfaceParts(host){
 const dark=materials.plastic(0x272a26,{roughness:.85}),ceramic=materials.plastic(0xb7a581,{roughness:.91}),metal=materials.metal(0xb7bbb2,{roughness:.5}),parts=[];
 // Only R1 and C1/C2 occur on the public interface schematic. Their package
 // envelopes and exact placement are concealed visual estimates.
 for(const[x,y,w,h,mat,name]of[[-10,-17.2,1.6,.8,dark,'R1 10K resistor'],[10,-17.2,1.6,.8,ceramic,'C1 100nF capacitor'],[13,-17.2,2.8,1.6,ceramic,'C2 22uF capacitor']]){
  parts.push(mesh(host.body,new THREE.BoxGeometry(w,h,.65),mat,[x,y,-2.675],'UHF RFID '+name+' physical body'));
  for(const sign of[-1,1])parts.push(mesh(host.body,new THREE.BoxGeometry(.28,h,.69),metal,[x+sign*(w/2-.14),y,-2.675],'UHF RFID interface passive metal termination'));
 }
 return parts;
}
export function buildUHFRFID(host){
 addCadParts(host,data,{shell:materials.plastic(0x444640,{roughness:.88})});
 const pcb=boards(host),rfModule=moduleAssembly(host),passives=interfaceParts(host);
 const socket=connector(host.body,56,false,{height:6});socket.name='UHF RFID blue open-top HY2.0-4P UART';socket.position.z=-1.75;socket.children[0].material.color.setHex(spec.grove.color);
 const tails=[];for(const x of[-3,-1,1,3])tails.push(mesh(host.body,new THREE.BoxGeometry(.42,.42,1.25),materials.metal(0xbdb18b,{roughness:.4}),[x,-20.85,-2.475],'UHF RFID Grove metal solder tail extension'));
 const port=host.add(new Port({id:'grove',label:'PORT.C · UART',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,6],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'RXD',color:'yellow'},{n:4,name:'TXD',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'UART',scope:'Physical socket, attachment and four-wire cable pose only; no UART, RF field, scan, tag identity, read/write, electrical or firmware behavior'}}));
 host.add(new Component({id:'sensor',label:'JRD-4035 ceramic antenna visual anchor',position:[0,2,3.35],meta:{role:'visual-anchor',part:'JRD-4035',scope:'Passive visual antenna/module anchor only; no RF field, tags, EPC, read/write, scan, RSSI, UART, AT commands or firmware behavior'}}));
 addStickers(host);host.uhfRfidAssembly={pcb,rfModule,passives,socket,tails,port};
}
