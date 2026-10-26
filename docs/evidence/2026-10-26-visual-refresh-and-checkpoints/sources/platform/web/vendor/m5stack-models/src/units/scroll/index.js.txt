import * as THREE from 'three';
import {Device,Module,Component,Button,Led,VisualJoint,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,grove,slab,screw} from '../../modeling/parts.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';

function addBoard(host){
 const w=9.8,h=13,r=3.8,post=3.8,offset=w-8,dy=Math.sqrt(post*post-offset*offset),theta=Math.acos(offset/post),shape=new THREE.Shape();
 shape.moveTo(-w+r,-h);shape.lineTo(-6.4,-h);shape.lineTo(-6.4,-8.6);shape.lineTo(6.4,-8.6);shape.lineTo(6.4,-h);shape.lineTo(w-r,-h);shape.absarc(w-r,-h+r,r,-Math.PI/2,0);
 shape.lineTo(w,-4-dy);shape.absarc(8,-4,post,-theta,theta-2*Math.PI,true);shape.lineTo(w,h-r);shape.absarc(w-r,h-r,r,0,Math.PI/2);shape.lineTo(-w+r,h);shape.absarc(-w+r,h-r,r,Math.PI/2,Math.PI);
 shape.lineTo(-w,-4+dy);shape.absarc(-8,-4,post,Math.PI-theta,-Math.PI+theta,true);shape.lineTo(-w,-h+r);shape.absarc(-w+r,-h+r,r,Math.PI,Math.PI*1.5);
 const bore=new THREE.Path();bore.absarc(0,-4,2.7,0,Math.PI*2,true);shape.holes.push(bore);
 // Source rays put the rear floor at -2.8 and central front-seat underside
 // at -0.2 mm. The board occupies that real cavity; its outline is inferred.
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(shape,{depth:.8,bevelEnabled:false,curveSegments:24}),materials.plastic(0x28513b,{roughness:.87}),[0,0,-1.5],'Scroll PCB with real post and Grove relief');host.parts.pcb=pcb;
 for(const [x,y,w,h]of [[0,3,3,3],[5,9,2,1.5]])slab(host.body,w,h,.6,.15,[x,y,-.7],materials.plastic(0x242a29),[],.025).name='Scroll fixed circuit package';
}
function build(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe4e7df,{roughness:.76}),wheel:materials.plastic(0xbc253b,{roughness:.7}),support:materials.plastic(0x333b37),lens:materials.plastic(0xdde8dc,{roughness:.32,transparent:true,opacity:.7})});
 addBoard(host);
 const wheel=parts['Scroll native wheel and axle'];
 const joint=host.add(new VisualJoint({id:'rotation',label:'Scroll wheel',position:spec.wheelCenter,axis:[1,0,0],continuous:true,meta:{axisEvidence:'Official U186 assembled STL wheel cylinder and EC10E product drawing; physical axis +X',demoRpmMax:60}}));joint.adopt(wheel);
 const press=host.add(new Button({id:'press',label:'Scroll wheel press',mesh:joint.object3d,travel:spec.travelMm,meta:{role:'visual-control',surfaceCenter:[0,6.4,14.9],surfaceFace:'front',travelSource:'0.25 mm appearance estimate; wheel and axle insert share the press group; concealed pivot/switch support motion unconfirmed'}}));
 // The source does not identify a fixed seat for this axle insert. Keep its
 // original fit with the shaft during visual pressing, without rotating it.
 // This actuator grouping is an appearance approximation, not physical CAD.
 const support=parts['Scroll native encoder axle support'];press.cap.attach(support);
 const pipe=parts['Scroll native RGB light pipe'];pipe.geometry.computeBoundingBox();const center=pipe.geometry.boundingBox.getCenter(new THREE.Vector3());pipe.geometry.translate(-center.x,-center.y,-center.z);
 const led=host.add(new Led({id:'rgb',label:'Scroll RGB',mesh:pipe,position:center.toArray(),glowSize:2.5,meta:{role:'externally-driven-visual',source:'Official U186 single WS2812C and original CAD light pipe; no encoder/press response'}}));led.glow.position.z=1.9;
 const socket=grove(host,spec.grove);socket.name='Scroll red Grove socket';
 // Official front views show an open upper socket, exposing four pins.
 const roof=socket.children.find(o=>o.geometry?.parameters?.height===.8&&o.position.y>0);
 if(!roof)throw new Error('Scroll Grove upper roof was not found');
 const red=roof.material;roof.removeFromParent();roof.geometry.dispose();
 mesh(socket,new THREE.BoxGeometry(3.4,.65,1.05),red,[0,1.1,-3.5],'Scroll Grove short latch bridge');
 for(const x of [-3,-1,1,3]){const metal=materials.metal(0xb9b397);mesh(host.body,new THREE.BoxGeometry(.42,2,.35),metal,[x,-9.2,-1.1],'Scroll fixed Grove solder tail');mesh(host.body,new THREE.BoxGeometry(.42,.45,1.05),metal,[x,-9.9,-.65],'Scroll fixed Grove contact bend');}
 screw(host.body,[0,-4,-4.015],'back',1.2);
 host.add(new Component({id:'sensor',label:'Unit Scroll visual anchor',meta:{role:'visual-anchor',scope:'no encoder counts, I2C, firmware, electrical or sensor model'}}));
 host.scrollMechanism={wheel,support,joint,press,led};
 addStickers(host);
}
export class Model extends Device{static meta={id:'m5stack.unit.scroll',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,nominalMm:spec.nominalMm,keymap:spec.keymap};build(){build(this);}}
export class GroveModule extends Module{static meta={id:'m5stack.unit.scroll.grove',name:spec.name,sku:spec.sku,connector:'grove',keymap:spec.keymap};build(options={}){buildGroveModuleAssembly(this,build,options);}}
export {spec};
export default Model;
