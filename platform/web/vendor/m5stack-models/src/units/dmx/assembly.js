import * as THREE from 'three';
import {Button,Component,Led,Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,screw,FACE,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';

const tau=Math.PI*2;
function hole(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,tau,false);shape.holes.push(h);}
function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:48}),material,position,name);}
function annulus(parent,outer,inner,depth,position,material,name){const s=new THREE.Shape();s.absarc(0,0,outer,0,-tau,true);hole(s,0,0,inner);return solid(parent,s,depth,position,material,name);}
class FixedRedLed extends Led{
 set(state){if(typeof state==='boolean')state={on:state};else if(typeof state==='string'||typeof state==='number')state={on:true};super.set({...state,color:0xff2820});}
}
function board(host){
 const s=new THREE.Shape(),x=10.5,y=22.5,r=3.45,dx=x-8,dy=Math.sqrt(r*r-dx*dx),a=Math.acos(dx/r);
 // Open reliefs around the two native mounting bosses; Grove notch at bottom.
 s.moveTo(-5.35,-y);s.lineTo(-x,-y);s.lineTo(-x,-12-dy);s.absarc(-8,-12,r,Math.PI+a,Math.PI-a,false);s.lineTo(-x,y);s.lineTo(x,y);s.lineTo(x,-12+dy);s.absarc(8,-12,r,a,tau-a,false);s.lineTo(x,-y);s.lineTo(5.35,-y);s.lineTo(5.35,-16.9);s.lineTo(-5.35,-16.9);s.closePath();hole(s,0,-12,2.1);
 const pcb=solid(host.body,s,.8,[0,0,-.4],materials.plastic(0x28503e,{roughness:.9}),'DMX physical PCB with open boss reliefs and Grove notch');pcb.userData={role:'physical-pcb',scope:'Reconstructed hidden board envelope; no traces or electronics simulation'};
 const dark=materials.plastic(0x202326,{roughness:.8}),metal=materials.metal(0xa6ada7,{roughness:.48});
 slab(host.body,7.5,10,2.7,.3,[0,0,.4],dark,[],.05).name='DMX CA-IS3092W isolated transceiver package';
 for(const x of[-4.1,4.1])for(let i=0;i<8;i++)mesh(host.body,new THREE.BoxGeometry(.65,.45,.3),metal,[x,(i-3.5)*1.1,.7],'DMX transceiver gull-wing lead');
 slab(host.body,2.5,3,.9,.2,[6,-5,.4],dark,[],.04).name='DMX ME6206 regulator package';
 return pcb;
}
function grove(host){
 const g=new THREE.Group();g.name='DMX cyan open-top HY2.0-4P UART socket';g.position.fromArray(spec.grove.position);g.quaternion.copy(FACE.bottom);host.body.add(g);
 const plastic=materials.plastic(spec.grove.color,{roughness:.61}),metal=materials.metal(0xb6aa82,{roughness:.42}),depth=6.6;
 const box=(size,p,name,material=plastic)=>mesh(g,new THREE.BoxGeometry(...size),material,p,'DMX Grove '+name);
 for(const sign of[-1,1]){box([.65,5.2,depth],[sign*4.675,0,-depth/2],'side wall');box([.7,.6,3.2],[sign*3.85,2.3,-4.9],'guide rail');box([.6,.45,1.2],[sign*3.65,2.375,-1.8],'latch shoulder');}
 box([8.7,.65,depth],[0,-2.275,-depth/2],'floor');box([8.7,4.55,.65],[0,.325,-depth+.325],'rear wall');box([4.8,.45,2.3],[0,2.375,-4.6],'locking bridge');
 for(let i=0;i<4;i++){box([.42,.42,4.7],[(i-1.5)*2,.2,-3.7],`contact ${i+1}`,metal);box([.42,1.4,.42],[(i-1.5)*2,-2.7,-6],`solder tail ${i+1}`,metal);}
 const port=host.add(new Port({id:'grove',label:'PORT.C · UART',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'UART_RX',color:'yellow'},{n:4,name:'UART_TX',color:'white'}],meta:{role:'visual-connector',face:'bottom',protocol:'UART',scope:'Physical attachment/cable pose only; no UART, DMX, isolated power or electrical simulation'}}));return{group:g,port};
}
function termination(host){
 const p=spec.termination.position,dark=materials.plastic(0x1d2323,{roughness:.78}),metal=materials.metal(0xa0a7a3,{roughness:.45});
 const body=slab(host.body,3.2,6,3.0,.2,[p[0],p[1],-.2],dark,[],.035);body.name='DMX fixed SS-1260 switch body';
 for(const y of[-1.6,0,1.6])mesh(host.body,new THREE.BoxGeometry(.45,.5,.9),metal,[p[0],p[1]+y,-.6],'DMX termination switch PCB terminal');
 const cap=slab(new THREE.Group(),1.65,1.65,1.0,.2,[0,0,0],dark,[],.035);cap.name='DMX physical SS-1260 sliding cap';
 const control=host.add(new Button({id:'termination',label:'120 Ω terminal switch',mesh:cap,latching:true,position:p,axis:spec.termination.axis,travel:spec.termination.travelMm,meta:{role:'visual-control',mechanism:'retained-slide',positions:['OFF','ON'],detentsMm:[0,spec.termination.travelMm],evidence:'SS-1260 and 120R from official schematic; direction from exact-product front photo, detent travel estimated',scope:'Retained visual position and input intent only; no resistor, bus or power state'}}));return{body,cap,control};
}
function xlr(host){
 const g=new THREE.Group();g.name='DMX fixed XLR-328P female receptacle';g.position.fromArray(spec.xlr.position);g.quaternion.copy(FACE.top);host.body.add(g);
 const black=materials.plastic(0x202222,{roughness:.78}),insertMat=materials.plastic(0x2a2c2a,{roughness:.85}),metal=materials.metal(0xb3b7b2,{roughness:.34}),gold=materials.metal(0xa69961,{roughness:.4});
 const barrel=annulus(g,10.45,9.9,19.6,[0,0,-19.6],black,'DMX true hollow XLR barrel');
 const rim=annulus(g,spec.xlr.outerRadiusMm,9.9,1.5,[0,0,-1.5],black,'DMX XLR mouth rim');
 const rear=solid(g,(()=>{const s=new THREE.Shape();s.absarc(0,0,9.9,0,-tau,true);return s;})(),1.2,[0,0,-19.6],black,'DMX XLR molded rear support');
 const insertShape=new THREE.Shape();insertShape.absarc(0,0,spec.xlr.insertRadiusMm,0,-tau,true);for(const[x,z]of spec.xlr.contactCentersMm)hole(insertShape,x,-z,spec.xlr.contactHoleRadiusMm);
 const insert=solid(g,insertShape,10,[0,0,-12],insertMat,'DMX XLR female insert with three true contact bores');
 const contacts=[];for(let i=0;i<3;i++){const[x,z]=spec.xlr.contactCentersMm[i];const sleeve=annulus(g,1.12,.73,6.2,[x,-z,-11.5],gold,`DMX XLR female spring contact ${i+1}`);contacts.push(sleeve);for(const sign of[-1,1])mesh(g,new THREE.BoxGeometry(.16,1.1,3.8),gold,[x+sign*.6,-z,-8],`DMX XLR contact ${i+1} spring leaf`);mesh(g,new THREE.BoxGeometry(.6,.65,6.8),metal,[x,-z,-15.6],`DMX XLR contact ${i+1} solder tail`);}
 // The key rib and fluted outer ribs remain solids, never a photograph across a hole.
 for(const angle of[-2.5,-1.5,-.6,.4,1.5,2.5]){const rib=mesh(g,new THREE.BoxGeometry(.65,1.1,17.5),black,[Math.cos(angle)*10.35,Math.sin(angle)*10.35,-10.1],'DMX XLR exterior axial rib');rib.rotation.z=angle-Math.PI/2;}
 mesh(g,new THREE.BoxGeometry(1.4,.8,3.2),black,[-5.5,-7.55,-2.2],'DMX XLR asymmetric insertion key');
 const ear=annulus(g,2.65,1.35,3.7,[-8.6,-8.6,-3.7],black,'DMX XLR open mounting ear');
 mesh(g,new THREE.BoxGeometry(3.0,2.0,3.7),black,[-7,-7.3,-1.85],'DMX XLR ear web');
 const latchGroup=new THREE.Group();latchGroup.name='DMX metal PUSH release linkage';
 slab(latchGroup,7.6,.55,4.0,1.2,[0,27.325,24],metal,[],.04).name='DMX PUSH metal paddle';
 mesh(latchGroup,new THREE.BoxGeometry(3.8,4.9,.55),metal,[0,24.9,24.25],'DMX PUSH bent connecting tongue');
 mesh(latchGroup,new THREE.BoxGeometry(3.4,1.5,2.6),metal,[0,22.5,22.8],'DMX PUSH latch stem');
 const release=host.add(new Button({id:'xlr-release',label:'XLR PUSH release',mesh:latchGroup,position:spec.release.position,axis:spec.release.axis,travel:spec.release.travelMm,meta:{role:'visual-control',mechanism:'momentary-connector-release',evidence:'Visible PUSH paddle and bent linkage from official side/end photographs; 1 mm inward axial visual travel estimated, not measured',scope:'Visible release travel/input intent only; does not latch, attach or electrically connect cables'}}));
 const port=host.add(new Port({id:'dmx',label:'XLR-3 female · DMX',connector:'xlr-3-male',position:spec.xlr.position,hitSize:[21.4,1,21.4],pins:[{n:1,name:'ISO_GND'},{n:2,name:'B',signal:'D-'},{n:3,name:'A',signal:'D+'}],meta:{role:'visual-connector',face:'top',matingGender:'male',fixed:true,scope:'Receptacle frame and physical pin metadata only; no DMX/RS-485 or plug accessory included'}}));
 return{group:g,barrel,rim,rear,insert,contacts,ear,release,port};
}
function indicator(host){
 const lens=slab(new THREE.Group(),1.45,3.4,.25,.55,[0,0,0],materials.plastic(0xc5cbc4,{roughness:.6}),[],.025);lens.name='DMX translucent indicator light guide';
 const led=host.add(new FixedRedLed({id:'power-led',label:'D4 red power indicator',mesh:lens,position:[8.4,-21.85,4],color:0xff2820,radius:.2,glowSize:2.2,meta:{role:'externally-driven-visual',colorMode:'fixed-red',evidence:'Official schematic D4 RED LED/R8 2K. Marketing image says RGB LED; no independent RGB channels in schematic.',scope:'Default off; externally supplied brightness only. No automatic power, termination or DMX activity response'}}));led.glow.position.z=.3;return led;
}
export function buildDMX(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0x626561,{roughness:.8})});
 const pcb=board(host),input=grove(host),switchAssembly=termination(host),xlrAssembly=xlr(host),powerLed=indicator(host);screw(host.body,[0,-12,-3.97],'back',1.4);
 host.add(new Component({id:'sensor',label:'DMX visual anchor',meta:{role:'visual-anchor',scope:'No DMX universe, register, UART, transceiver, resistor, firmware or electrical state'}}));
 addStickers(host);
 host.dmxAssembly={parts,pcb,input,switchAssembly,xlr:xlrAssembly,powerLed};
}
