import * as THREE from 'three';
import {Port,Button,materials,geometry} from '../../core/index.js';
import {usbA,usbC,microSD,audioJack} from '../../modeling/connectors.js';
import {slab,mesh,grove,header,FACE,portQuaternion} from '../../modeling/parts.js';
import {DIM} from './dimensions.js';

function portGroup(host,{id,label,connector,position,face,w,h}){
 const group=new THREE.Group();group.name=label;group.position.fromArray(position);group.quaternion.copy(FACE[face]);host.body.add(group);
 host.add(new Port({id,label,connector,position,quaternion:portQuaternion(face),hitSize:[w,1,h],meta:{face,role:'visual-connector'}}));return group;
}
function hdmiProfile(w,h){
 const s=new THREE.Shape();s.moveTo(-w/2,-h/2);s.lineTo(w/2,-h/2);s.lineTo(w/2,h/2-1);s.lineTo(w/2-1,h/2);s.lineTo(-w/2+1,h/2);s.lineTo(-w/2,h/2-1);s.closePath();return s;
}
function hdmi(host){
 const g=portGroup(host,{id:'hdmi',label:'HDMI Type-A display output',connector:'hdmi',position:DIM.ports.hdmi,face:'left',w:14.3,h:5.2});
 const outer=hdmiProfile(14.3,5.2),inner=hdmiProfile(13.6,4.5);outer.holes.push(new THREE.Path(inner.getPoints().reverse()));
 mesh(g,new THREE.ExtrudeGeometry(outer,{depth:7.5,bevelEnabled:false}),materials.metal(0xa6b1ad,{roughness:.38}),[0,0,-7.46],'Full-size HDMI shaped shield');
 mesh(g,new THREE.BoxGeometry(13.6,4.5,.35),materials.plastic(0x111b17,{roughness:.91}),[0,0,-7.65],'HDMI dielectric backstop');
 slab(g,10.1,.7,5.7,.18,[0,0,-7.15],materials.plastic(0x1b211d,{roughness:.84}),[],.04).name='HDMI contact tongue';
 for(let i=0;i<19;i++)mesh(g,new THREE.BoxGeometry(.22,.09,2.2),materials.metal(0xb9ae82,{roughness:.45}),[(i-9)*.48,i%2?.42:-.42,-3.5],'HDMI contact pad');
 return g;
}
function rj45Hole(){
 const p=new THREE.Path();p.moveTo(-6.6,4.5);p.lineTo(6.6,4.5);p.lineTo(6.6,-1.8);p.lineTo(5.6,-1.8);p.lineTo(5.6,-3.8);p.lineTo(3.8,-3.8);p.lineTo(3.8,-5.3);p.lineTo(-3.8,-5.3);p.lineTo(-3.8,-3.8);p.lineTo(-5.6,-3.8);p.lineTo(-5.6,-1.8);p.lineTo(-6.6,-1.8);p.closePath();return p;
}
function ethernet(host){
 const g=portGroup(host,{id:'ethernet',label:'10/100 Ethernet RJ45',connector:'ethernet-rj45',position:DIM.ports.ethernet,face:'right',w:16.2,h:13.4});
 for(const [w,h,depth,z,material,name]of [[16.2,13.4,11.8,-11.76,materials.metal(0x8b9691,{roughness:.44}),'RJ45 metal shield'],[15.7,12.9,11.2,-11.5,materials.plastic(0x111a16,{roughness:.87}),'RJ45 keyed plastic frame']]){
  const shape=geometry.roundedRect(w,h,.35);shape.holes.push(rj45Hole());mesh(g,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false}),material,[0,0,z],name);
 }
 mesh(g,new THREE.BoxGeometry(13.2,10.5,.4),materials.plastic(0x0b130f,{roughness:.96}),[0,0,-12],'RJ45 deep backstop');
 for(let i=0;i<8;i++){
  const x=(i-3.5)*1.15,curve=new THREE.CatmullRomCurve3([[x,4.1,-1.0],[x,3.8,-2.2],[x,1.7,-4.8]].map(p=>new THREE.Vector3(...p)));
  mesh(g,new THREE.TubeGeometry(curve,16,.13,6,false),materials.metal(0xbbaa68,{roughness:.4}),[0,0,0],`RJ45 spring contact ${i+1}`);
 }
 for(const [x,color]of [[-5.5,0x9c8e36],[5.5,0x417943]])slab(g,2.0,1.1,.6,.2,[x,-5.35,-.75],materials.glossy(color,{roughness:.35}),[],.07).name='Ethernet indicator lens';
 return g;
}

export function addPorts(host){
 usbC(host,{id:'usb-c',position:DIM.ports.usbC,face:'right',w:8.7,h:3.1,depth:4.5});
 usbC(host,{id:'usb-c2',position:DIM.ports.usbC2,face:'left',w:8.7,h:3.1,depth:4.5});
 host.get('usb-c').label='USB-C1 · OTG';host.get('usb-c2').label='USB-C2 · 5 V input';
 const a=usbA(host,{id:'usb-a',position:DIM.ports.usbA,face:'right',w:13.2,h:5.8,depth:8.4});
 a.getObjectByName('USB-A lower tongue').material=materials.plastic(0x137ca7,{roughness:.78});
 hdmi(host);ethernet(host);
 grove(host,{id:'grove',position:DIM.ports.grove,face:'left',w:10,h:5.2,color:0xdce0d7,depth:6.4});
 audioJack(host,{id:'headset',position:DIM.ports.audio,face:'left',diameter:5.2,bore:3.5,depth:7});
 header(host.body,{position:DIM.ports.ext,face:'top',cols:7,rows:2,pitch:2.54});
 host.add(new Port({id:'ext',label:'EXT 2.54-14P',connector:'2.54-14p',position:DIM.ports.ext,quaternion:portQuaternion('top'),hitSize:[18.3,1,5.6],meta:{face:'top',role:'visual-connector'}}));
 microSD(host,{id:'micro-sd',position:DIM.ports.sd,face:'top',w:12.2,h:1.5,depth:5});
 const boot=new THREE.Mesh(geometry.roundedSlab({w:5.6,h:6.3,depth:.4,radius:.8,bevel:.12}),materials.plastic(0xcdd2cb,{roughness:.76}));
 host.add(new Button({id:'boot',label:'Boot key',position:[41.85,.4,5.6],quaternion:FACE.right,mesh:boot,travel:.16,axis:[0,0,-1],meta:{role:'visual-control'}}));
 const ir=new THREE.Group();ir.position.set(30.4,26.4,6.2);ir.quaternion.copy(FACE.top);ir.name='Top IR receiver package';host.body.add(ir);
 slab(ir,5.4,2.0,.3,.25,[0,0,0],materials.plastic(0x151e18),[],.04);
 for(const x of [-1.3,1.3])mesh(ir,new THREE.SphereGeometry(.65,20,12),materials.glossy(0x171f18,{roughness:.22}),[x,0,.15],'IR optical window');
 const emitter=mesh(host.body,new THREE.SphereGeometry(.6,20,12),materials.glossy(0x252e21,{roughness:.24}),[-34.5,26.65,6.1],'Top IR emitter lens');emitter.scale.y=.6;
 return {usbA:a};
}
