import * as THREE from 'three';
import {materials,Port} from '../core/index.js';
import {roundedRect} from '../core/geometry.js';
import {FACE,portQuaternion,mesh,slab} from './parts.js';

// Appearance geometry, not electrical or protocol models. Concealed package
// depths are photo-derived; place each insert using the product's actual opening.
function connectorGroup(host,{id,label,connector,position,face,w,h,depth}){
 const group=new THREE.Group();group.position.fromArray(position);group.quaternion.copy(FACE[face]);group.name=label;group.userData={role:'visual-connector',visualFamily:connector,depthMm:depth};host.body.add(group);
 if(id)host.add(new Port({id,label,connector,position,quaternion:portQuaternion(face),hitSize:[w,1,h],meta:{role:'visual-connector',face}}));
 return group;
}
function shell(group,{w,h,r,wall,depth,name,color=0xa8adac}){
 const shape=roundedRect(w,h,r);shape.holes.push(roundedRect(w-2*wall,h-2*wall,Math.max(.04,r-wall),{path:new THREE.Path(),clockwise:true}));
 return mesh(group,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:20}),materials.metal(color,{roughness:.38}),[0,0,-depth+.04],name);
}
function back(group,w,h,depth,name){return mesh(group,new THREE.BoxGeometry(w,h,.3),materials.plastic(0x111716,{roughness:.94}),[0,0,-depth-.15],name);}

export function usbA(host,{id='usb-a',position,face='left',w=13.2,h=5.5,depth=6.5}={}){
 const group=connectorGroup(host,{id,label:'USB-A receptacle',connector:'usb-a',position,face,w,h,depth});
 shell(group,{w,h,r:.24,wall:.28,depth,name:'USB-A rectangular metal shell'});back(group,w-.55,h-.55,depth,'USB-A dielectric backstop');
 slab(group,w*.76,1.3,depth-.9,.18,[0,-.9,-depth+.2],materials.plastic(0x171c1b,{roughness:.88}),[],.04).name='USB-A lower tongue';
 for(const x of [-3,-1,1,3])mesh(group,new THREE.BoxGeometry(.65,.08,3.6),materials.metal(0xc1ae75,{roughness:.4}),[x,-.18,-2.7],'USB-A contact pad');
 for(const x of [-3.3,3.3]){
  const spring=mesh(group,new THREE.BoxGeometry(1,.12,1.5),materials.metal(0x939b97,{roughness:.45}),[x,h/2-.42,-1.5],'USB-A retention spring');spring.rotation.x=-.15;
 }
 return group;
}

export function usbC(host,{id='usb',position,face='left',w=8.7,h=3.1,depth=3.5}={}){
 const group=connectorGroup(host,{id,label:'USB-C receptacle',connector:'usb-c',position,face,w,h,depth});
 shell(group,{w,h,r:h/2,wall:.23,depth,name:'USB-C capsule metal shell'});back(group,w-.46,h-.46,depth,'USB-C dielectric backstop');
 const tongue=slab(group,w*.73,.6,depth-.65,.2,[0,0,-depth+.2],materials.plastic(0x141a19,{roughness:.88}),[],.035);tongue.name='USB-C centered tongue';
 for(const y of [-.34,.34])for(let i=0;i<12;i++)mesh(group,new THREE.BoxGeometry(.24,.06,1.7),materials.metal(0xbdb18d,{roughness:.44}),[(i-5.5)*.5,y,-1.85],'USB-C contact pad');
 return group;
}

export function microSD(host,{id='micro-sd',position,face='right',w=17.5,h=1.5,depth=5}={}){
 const group=connectorGroup(host,{id,label:'microSD receptacle',connector:'micro-sd',position,face,w,h,depth});
 shell(group,{w,h,r:.16,wall:.22,depth,name:'microSD rectangular shield'});back(group,w-.44,h-.44,depth,'microSD insulating backstop');
 mesh(group,new THREE.BoxGeometry(w-.8,.16,depth-.3),materials.plastic(0x161c19,{roughness:.9}),[0,-h/2+.3,-depth/2],'microSD lower guide bed');
 for(const sign of [-1,1])mesh(group,new THREE.BoxGeometry(.35,.32,depth-.5),materials.plastic(0x1b211e),[sign*(w/2-.65),-.12,-depth/2],'microSD card-edge guide');
 for(let i=0;i<8;i++)mesh(group,new THREE.BoxGeometry(.48,.08,1.2),materials.metal(0xc0aa70,{roughness:.4}),[(i-3.5)*1.1,-h/2+.44,-depth+1],'microSD spring contact');
 return group;
}

export function audioJack(host,{id='headset',position,face='left',diameter=5.2,bore=3.5,depth=7}={}){
 const group=connectorGroup(host,{id,label:'3.5 mm audio jack',connector:'audio-3.5mm',position,face,w:diameter,h:diameter,depth});
 const ring=new THREE.Shape();ring.absarc(0,0,diameter/2,0,Math.PI*2,false);const hole=new THREE.Path();hole.absarc(0,0,bore/2,0,Math.PI*2,true);ring.holes.push(hole);
 mesh(group,new THREE.ExtrudeGeometry(ring,{depth:depth+.12,bevelEnabled:false,curveSegments:48}),materials.plastic(0x111615,{roughness:.68}),[0,0,-depth],'Audio jack bored housing');
 mesh(group,new THREE.CylinderGeometry(bore/2,bore/2,.3,48).rotateX(Math.PI/2),materials.plastic(0x080b0a,{roughness:.98}),[0,0,-depth-.15],'Audio jack deep backstop');
 for(const [i,z]of [-2.1,-4.2,-5.8].entries()){
  const leaf=mesh(group,new THREE.TorusGeometry(bore/2-.14,.11,8,24,Math.PI*.55),materials.metal(0xb8ad89,{roughness:.45}),[0,0,z],'Audio jack spring contact');leaf.rotation.z=i*2.2+.15;
 }
 return group;
}
