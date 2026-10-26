import * as THREE from 'three';
import {materials,Port} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {slab,mesh,disc,FACE,portQuaternion} from '../../modeling/parts.js';

/** Visible KF128-style construction. Concealed cage depths are photo-derived, not manufacturing dimensions. */
function terminalBank(parent,{id,x,y,count,width,color,sign,labels}){
 const group=new THREE.Group();group.position.set(x,y,0);group.name=`${id} terminal bank`;group.userData={role:'terminal-bank',id,poles:count,pitchMm:5,face:sign>0?'top':'bottom'};parent.add(group);
 const plastic=materials.plastic(color,{roughness:.78}),metal=materials.metal(0xa4aba8,{roughness:.39}),slotFloor=materials.metal(0x4d5553,{roughness:.67});
 const centers=Array.from({length:count},(_,i)=>(i-(count-1)/2)*5);
 slab(group,width,13,7.3,.3,[0,0,1.7],plastic,[],.08).name='Molded terminal base';
 slab(group,width,13,1.7,.3,[0,0,14.2],plastic,centers.map(cx=>({w:3.9,h:3.9,r:1.95,cx})),.045).name='Drilled screw-access rim';
 slab(group,width,6.5,5.2,.2,[0,-sign*3.25,9],plastic,[],.04).name='Terminal rear support';
 // Each side entry has a solid frame, continuous side walls, and a metal cage recessed 6.1 mm.
 for(let i=0;i<=count;i++)mesh(group,new THREE.BoxGeometry(.65,6.5,5.2),plastic,[(i-count/2)*5,sign*3.25,11.6],'Molded channel partition');
 for(let i=0;i<count;i++){
  const pole=new THREE.Group();pole.position.x=centers[i];pole.name=`${id}/${labels[i]}`;pole.userData={role:'terminal-pole',id:pole.name,face:sign>0?'top':'bottom',screwCenterMm:[x+centers[i],y,15.6],wireEntryMm:[x+centers[i],y+sign*6.5,11.6],entryNormal:[0,sign,0],clampDepthMm:6.1};group.add(pole);
  const entry=new THREE.Group();entry.position.set(0,sign*6.5,11.6);entry.quaternion.copy(sign>0?FACE.top:FACE.bottom);entry.name='Wire entry';pole.add(entry);
  slab(entry,5,5.6,.8,.18,[0,0,-.8],plastic,[{w:3.35,h:3.2,r:.12}],.05).name='Open wire-entry frame';
  // A U-shaped clamp and its rear web remain visible inside the square channel.
  mesh(pole,new THREE.BoxGeometry(3.15,4.8,.28),metal,[0,sign*2.4,10.16],'Clamp lower plate');
  for(const sx of [-1,1])mesh(pole,new THREE.BoxGeometry(.25,4.8,2.85),metal,[sx*1.45,sign*2.4,11.45],'Clamp side wall');
  mesh(pole,new THREE.BoxGeometry(3.15,.32,2.85),metal,[0,sign*.24,11.45],'Clamp rear web');
  mesh(pole,new THREE.BoxGeometry(2.7,3.8,.32),metal,[0,sign*1.9,12.76],'Metal pressure plate');
  mesh(pole,new THREE.CylinderGeometry(.68,.68,2.05,24).rotateX(Math.PI/2),metal,[0,0,13.925],'Screw shank');
  const head=new THREE.Group();head.position.set(0,0,14.9);head.rotation.z=[.23,-.34,.57,-.18,.42][i%5];head.name='Recessed slotted screw';pole.add(head);
  mesh(head,new THREE.CylinderGeometry(1.7,1.7,.25,48).rotateX(Math.PI/2),slotFloor,[0,0,.125],'Slot bottom and screw base');
  const profile=new THREE.Shape();profile.absarc(0,0,1.7,0,Math.PI*2,false);profile.holes.push(roundedRect(2.8,.45,.08,{path:new THREE.Path(),clockwise:true}));
  mesh(head,new THREE.ExtrudeGeometry(profile,{depth:.45,bevelEnabled:true,bevelThickness:.025,bevelSize:.025,bevelSegments:2,curveSegments:32}),metal,[0,0,.25],'Slotted metal screw head');
 }
 return group;
}

export function stamplcTerminals(parent){
 terminalBank(parent,{id:'input-power',x:-13.7,y:31.3,count:3,width:15,color:0xb4302d,sign:1,labels:['vin','gnd','com']});
 terminalBank(parent,{id:'digital-input',x:13.8,y:31.3,count:8,width:40,color:0x1552ae,sign:1,labels:Array.from({length:8},(_,i)=>`in${i+1}`)});
 [-25.5,-8.4,8.8,25.9].forEach((x,i)=>terminalBank(parent,{id:`relay-${i+1}`,x,y:-30.1,count:3,width:15.8,color:0x777e79,sign:-1,labels:['no','com','nc']}));
}

export function stamplcDC(host){
 const position=[-28,37.65,13.2],jack=new THREE.Group();jack.position.fromArray(position);jack.quaternion.copy(FACE.top);jack.name='DC5521 input jack';jack.userData={role:'visual-connector',connector:'dc5521',boreDiameterMm:5.5,centerPinDiameterMm:2.1};host.body.add(jack);
 const black=materials.plastic(0x171a19,{roughness:.7});
 slab(jack,10.4,7.1,8,.25,[0,0,-8.1],black,[{w:5.6,h:5.6,r:2.8}],.05).name='Bored DC jack body';
 const ring=new THREE.Shape();ring.absarc(0,0,2.79,0,Math.PI*2,false);const bore=new THREE.Path();bore.absarc(0,0,2.75,0,Math.PI*2,true);ring.holes.push(bore);
 mesh(jack,new THREE.ExtrudeGeometry(ring,{depth:5.2,bevelEnabled:false,curveSegments:48}),materials.metal(0x676b65,{roughness:.55}),[0,0,-6.3],'DC socket metal sleeve');
 disc(jack,2.8,[0,0,-7.2],materials.plastic(0x0b0d0c)).name='Deep DC jack back';
 mesh(jack,new THREE.CylinderGeometry(1.05,1.05,4.3,40).rotateX(Math.PI/2),materials.metal(0xb6bbac,{roughness:.35}),[0,0,-3.95],'Recessed 2.1 mm center pin');
 host.add(new Port({id:'dc',label:'DC5521 · 6–36 V',connector:'dc5521',position,quaternion:portQuaternion('top'),hitSize:[10.4,1,7.1],meta:{role:'visual-connector',face:'top'}}));
 return jack;
}
