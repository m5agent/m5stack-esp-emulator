import * as THREE from 'three';
import {Button,Led,Port,Component,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {FACE,mesh,portQuaternion,screw} from '../../modeling/parts.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
import {spec,CHANNELS} from './dimensions.js';
function bore(shape,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,Math.PI*2,false);shape.holes.push(p);}
function cylinder(parent,r,depth,position,material,name){return mesh(parent,new THREE.CylinderGeometry(r,r,depth,48).rotateX(Math.PI/2),material,position,name);}
function board(host){
 const s=new THREE.Shape(),x=10.4,r=3.6,dy=Math.sqrt(r*r-(x-8)**2),a=Math.acos((x-8)/r);
 // Clockwise outside; four open scallops preserve the native corner bosses.
 s.moveTo(-x,42.3);s.lineTo(-5.6,42.3);s.lineTo(-5.6,36.6);s.lineTo(5.6,36.6);s.lineTo(5.6,42.3);s.lineTo(x,42.3);
 for(const y of[32,-32]){s.lineTo(x,y+dy);s.absarc(8,y,r,a,Math.PI*2-a,false);}
 s.lineTo(x,-42.3);s.lineTo(5.6,-42.3);s.lineTo(5.6,-36.6);s.lineTo(-5.6,-36.6);s.lineTo(-5.6,-42.3);s.lineTo(-x,-42.3);
 for(const y of[-32,32]){s.lineTo(-x,y-dy);s.absarc(-8,y,r,Math.PI+a,Math.PI*3-a,false);}s.closePath();
 for(const y of[-32,32])bore(s,0,y,2.0);
 for(let i=0;i<7;i++)bore(s,6.462,-20.4+6.8*i,1.0);
 bore(s,-7.9,38.2,1.35);
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:32}),materials.plastic(0x214d3c,{roughness:.9}),[0,0,-2.6],'ByteButton physical PCB with open boss/Grove relief');pcb.userData={role:'physical-pcb',scope:'Concealed visual reconstruction; no production traces or circuitry'};
 for(const y of[-32,32])screw(host.body,[0,y,-5.98],'back',1.35);
 const dark=materials.plastic(0x202825,{roughness:.85});
 mesh(host.body,new THREE.BoxGeometry(4,4,.8),dark,[-4,0,-3.03],'ByteButton concealed STM32G031 package');
 for(const y of[-12,12])mesh(host.body,new THREE.BoxGeometry(1.6,2.8,.6),dark,[-5,y,-2.99],'ByteButton concealed power/passive package');
 return pcb;
}
function socket(host,id,face,position){
 const group=new THREE.Group();group.name=`ByteButton ${id} red open-top HY2.0-4P`;group.position.fromArray(position);group.quaternion.copy(FACE[face]);host.body.add(group);
 const red=materials.plastic(spec.grove.color,{roughness:.6}),metal=materials.metal(0xb8ad89,{roughness:.43}),depth=spec.grove.depthMm;
 const box=(size,p,name,material=red)=>mesh(group,new THREE.BoxGeometry(...size),material,p,`ByteButton ${id} ${name}`);
 for(const sign of[-1,1]){box([.7,5.2,depth],[sign*4.65,0,-depth/2],'side wall');box([.9,.8,depth],[sign*3.85,2.2,-depth/2],'upper rail');}
 box([8.6,.7,depth],[0,-2.25,-depth/2],'floor');box([8.6,5.2,.6],[0,0,-depth+.3],'rear wall');box([8.6,2.7,4.65],[0,-1.25,-4.175],'recessed contact support');box([3.4,.65,3],[0,1.2,-4.95],'locking tongue');
 for(let i=0;i<4;i++)box([.42,.42,1.2],[(i-1.5)*2,-.15,-1.25],`contact ${i+1}`,metal).userData.pin=i+1;
 const port=host.add(new Port({id,label:id==='grove'?'PORT.A input · I2C':'PORT.A cascade · I2C',connector:'grove',position,quaternion:portQuaternion(face),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'SDA',color:'yellow'},{n:4,name:'SCL',color:'white'}],meta:{role:'visual-connector',face,usage:id==='grove'?'module-input':'cascade-output',scope:'Physical connection and cable pose only; two parallel Grove jacks have no simulated I2C or electrical behavior'}}));return{group,port};
}
function button(host,item){
 const{number,channel,y}=item,dark=materials.plastic(0x101614,{roughness:.75}),metal=materials.metal(0xb7bbb4,{roughness:.5});
 // Fixed 3×4×2.5 tactile package underneath the real front-shell aperture.
 const fixed=mesh(host.body,new THREE.BoxGeometry(4,3,2.5),dark,[0,y,-.55],`ByteButton CH${channel} fixed tactile package`);
 const cover=new THREE.Shape();cover.moveTo(-1.9,-1.4);cover.lineTo(-1.9,1.4);cover.lineTo(1.9,1.4);cover.lineTo(1.9,-1.4);cover.closePath();bore(cover,0,0,.95);
 mesh(host.body,new THREE.ExtrudeGeometry(cover,{depth:.15,bevelEnabled:false,curveSegments:24}),metal,[0,y,.7],`ByteButton CH${channel} bored fixed tactile metal cover`);
 for(const x of[-2.2,2.2])mesh(host.body,new THREE.BoxGeometry(.55,1.2,.2),metal,[x,y,-1.65],`ByteButton CH${channel} tactile terminal`);
 const cap=new THREE.Group();cap.name=`ByteButton CH${channel} moving cap and actuator stem`;
 cylinder(cap,2.05,2,[0,0,1],dark,`ByteButton CH${channel} solid black button cap`);
 cylinder(cap,.8,5,[0,0,-2.5],dark,`ByteButton CH${channel} moving button stem`);
 const control=host.add(new Button({id:item.button,label:`CH${channel} momentary button`,mesh:cap,position:[0,y,6],travel:spec.button.travelMm,axis:spec.button.axis,longPressMs:0,meta:{role:'visual-control',channel,visualMotion:'linear',travelEvidence:'0.2 mm appearance estimate; official drawing fixes 2 mm external cap projection but gives no stroke or cap/stem production geometry',scope:'Input intent and real cap/stem press/release only; no switch state machine, bus, debounce or automatic RGB response'}}));return{control,cap,fixed};
}
function lights(host){
 const result=[];
 for(const item of CHANNELS){const lens=host.parts[`ByteButton CH${item.channel} native RGB exit face`];lens.material=materials.plastic(0xc5cbbf,{roughness:.5});
 const led=host.add(new Led({id:item.rgb,label:`CH${item.channel} external RGB`,mesh:lens,radius:.4,glowSize:2.5,meta:{role:'externally-driven-visual',channel:item.channel,mapping:'Physical CH0–CH7 location; not a claim about U1–U9 serial order',scope:'External colour/brightness only; no automatic key, power or firmware response'}}));led.glow.position.set(9.6,item.y,6.02);result.push(led);
 // Package on the PCB beneath the original lightpipe; its retaining pin bores stay open.
 mesh(host.body,new THREE.BoxGeometry(2,2,.8),materials.plastic(0xd4d6cc,{roughness:.7}),[6.5,item.y,-1.4],`ByteButton CH${item.channel} fixed WS2812C-2020 package`);
 }
 const lens=host.parts['ByteButton native end RGB lightpipe'];lens.material=materials.plastic(0xbac3b9,{roughness:.5});
 const led=host.add(new Led({id:'rgb-9',label:'End external RGB',mesh:lens,radius:.35,glowSize:2,meta:{role:'externally-driven-visual',mapping:'Physical end indicator; not a claim about U1–U9 serial order',scope:'External colour/brightness only; no automatic response'}}));led.glow.position.set(-7.9,43.81,.2);result.push(led);
 mesh(host.body,new THREE.BoxGeometry(2,2,.8),materials.plastic(0xd4d6cc,{roughness:.7}),[-7.9,40.3,-1.4],'ByteButton end WS2812C-2020 package');return result;
}
export function buildBytebutton(host){
 addCadParts(host,data,{shell:materials.plastic(0x575b55,{roughness:.84}),lightpipe:materials.plastic(0xc5cbbf,{roughness:.54})});
 const pcb=board(host),input=socket(host,'grove','bottom',spec.grove.position),output=socket(host,'grove-out','top',spec.grove.outputPosition),buttons=CHANNELS.map(item=>button(host,item)),leds=lights(host);
 host.add(new Component({id:'sensor',label:'ByteButton appearance anchor',meta:{role:'visual-anchor',scope:'No registers, sensor values, I2C or firmware behavior'}}));host.bytebuttonAssembly={pcb,input,output,buttons,leds};
 host.byteStickers=addStickers(host);
}
