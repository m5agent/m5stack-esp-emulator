import * as THREE from 'three';
import {Port,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,portQuaternion} from '../../modeling/parts.js';
import data from './geometry-data.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';
const tau=Math.PI*2;
function bore(s,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,tau,false);s.holes.push(h);}
function solid(parent,s,d,p,m,n){return mesh(parent,new THREE.ExtrudeGeometry(s,{depth:d,bevelEnabled:false,curveSegments:40}),m,p,n);}
function ring(parent,outer,inner,depth,p,m,n){const s=new THREE.Shape();s.absarc(0,0,outer,0,tau,false);bore(s,0,0,inner);return solid(parent,s,depth,p,m,n);}
function cylinder(parent,r,depth,p,m,n,topR=r){return mesh(parent,new THREE.CylinderGeometry(topR,r,depth,48).rotateX(Math.PI/2),m,p,n);}
function board(host){
 const s=new THREE.Shape(),edge=10.4,cy=-16,r=3.5,a=Math.acos((edge-8)/r),dy=Math.sqrt(r*r-(edge-8)**2);
 s.moveTo(-edge,25.3);s.lineTo(-9.2,26.5);s.lineTo(9.2,26.5);s.lineTo(edge,25.3);s.lineTo(edge,cy+dy);s.absarc(8,cy,r,a,tau-a,false);s.lineTo(edge,-25);s.lineTo(9.2,-26.3);s.lineTo(5.5,-26.3);s.lineTo(5.5,-24.2);s.lineTo(-5.5,-24.2);s.lineTo(-5.5,-26.3);s.lineTo(-9.2,-26.3);s.lineTo(-edge,-25);s.lineTo(-edge,cy-dy);s.absarc(-8,cy,r,Math.PI+a,Math.PI-a,false);s.lineTo(-edge,25.3);s.closePath();bore(s,0,-16,1.05);
 const holes=[];for(const {center:[x,y]}of spec.transducers)for(const sign of[-1,1]){const q=[x+sign*4.6,y,.47];holes.push(q);bore(s,...q);}
 const green=materials.plastic(0x15794a,{roughness:.9}),tin=materials.metal(0xb9c3b2,{roughness:.42}),dark=materials.plastic(0x1c241e,{roughness:.87}),ceramic=materials.plastic(0xb5ad89,{roughness:.9}),top=spec.pcb.topZ,bottom=top-spec.pcb.thicknessMm;
 const pcb=solid(host.body,s,spec.pcb.thicknessMm,[0,0,bottom],green,'Ultrasonic-IO own GPIO carrier PCB with actual transducer solder bores,mount reliefs andfixing bore');pcb.userData={role:'physical-pcb',installedPoseInferred:true};
 const pads=[],barrels=[];for(const[x,y,r]of holes){pads.push(ring(host.body,.88,.32,.05,[x,y,top],tin,'Ultrasonic-IO actual front transducer solder annulus'));pads.push(ring(host.body,.88,.32,.05,[x,y,bottom-.05],tin,'Ultrasonic-IO actual rear transducer solder annulus'));barrels.push(ring(host.body,r,.32,spec.pcb.thicknessMm,[x,y,bottom],tin,'Ultrasonic-IO actual transducer plated solder bore'));}
 const chip=slab(host.body,4.7,9.6,1.2,.12,[0,7.5,-2.45],dark,[],.015);chip.name='Ultrasonic-IO real RCWL-9620 SOP16 package onown GPIO board rear,placement inferred';
 const chipLeads=[];for(const sign of[-1,1])for(let i=0;i<8;i++)chipLeads.push(mesh(host.body,new THREE.BoxGeometry(1.0,.45,.12),tin,[sign*2.7,7.5+(i-3.5)*1.27,-1.31],'Ultrasonic-IO RCWL-9620 actual package solder lead'));
 const passives=[];for(const[x,y,h,w]of[[5.7,7.8,1.6,.8],[7.5,7.8,1.6,.8],[9.0,7.8,1.6,.8],[5.0,4.1,1.7,.9],[-5.5,4.7,1.7,.9],[-3.8,-.2,.8,1.6],[-1.9,-.2,.8,1.6],[.1,-.2,.8,1.6],[2.0,-.2,.8,1.6],[3.9,-.2,.8,1.6],[5.8,-.2,.8,1.6]]){
  const q=slab(host.body,w,h,.42,.03,[x,y,-1.67],ceramic,[],.006);q.name='Ultrasonic-IO actual visible fixed photo-reference passive,package/installation inferred';passives.push(q);for(const sign of[-1,1])mesh(host.body,new THREE.BoxGeometry(w,.25,.08),tin,[x,y+sign*(h/2-.1),-1.3],'Ultrasonic-IO passive real solder end');
 }
 const configLinks=[];for(const y of[-9.1,-10.7])for(const x of[-.65,1.1])configLinks.push(mesh(host.body,new THREE.BoxGeometry(.9,.95,.08),tin,[x,y,-1.29],'Ultrasonic-IO own GPIO populated configuration land,not interactive'));
 const regulator=slab(host.body,2.9,1.6,.65,.07,[5.9,-24.5,-1.9],dark,[],.012);regulator.name='Ultrasonic-IO actual rear three-terminal support package seen inown boardphoto';for(const x of[4.85,5.9,6.95])mesh(host.body,new THREE.BoxGeometry(.45,.65,.1),tin,[x,-23.7,-1.3],'Ultrasonic-IO actual fixed support package solder foot');
 const grovePads=[];for(let i=0;i<4;i++)grovePads.push(mesh(host.body,new THREE.BoxGeometry(.85,.85,.025),tin,[(i-1.5)*2,-22.8,top+.0125],'Ultrasonic-IO actual Grove fixed PCB solder land '+(i+1)));
 return{pcb,holes,pads,barrels,chip,chipLeads,passives,configLinks,regulator,grovePads};
}
function acousticCarrier(host,{id,center:[x,y]}){
 const f=spec.acoustic,frame=new THREE.Group();frame.name='Ultrasonic-IO actual passive '+id+' acoustic carrier';frame.position.set(x,y,0);frame.userData={role:'passive-acoustic-carrier',id,noAnimatedMembrane:true};host.body.add(frame);
 const black=materials.plastic(0x171a17,{roughness:.66}),screen=materials.metal(0x232824,{roughness:.73}),silver=materials.metal(0xd1d3cc,{roughness:.56}),tin=materials.metal(0xa6b2a0,{roughness:.45});
 const housing=ring(frame,f.outerRadiusMm,f.innerRadiusMm,f.topZ-f.baseZ,[0,0,f.baseZ],black,'Ultrasonic-IO '+id+' actual thick black can wall andraised rim');
 const floor=cylinder(frame,7.98,.2,[0,0,f.baseZ+.1],black,'Ultrasonic-IO '+id+' physical closed can bottom');
 const support=ring(frame,6,4.9,.25,[0,0,2.45],black,'Ultrasonic-IO '+id+' recessed diaphragm support annulus');
 const supports=[];for(let i=0;i<3;i++){const a=i*tau/3;supports.push(cylinder(frame,.4,2.6,[Math.cos(a)*5.55,Math.sin(a)*5.55,1.15],black,'Ultrasonic-IO '+id+' internal support post'));}
 const diaphragm=cylinder(frame,f.diaphragmRadiusMm,.2,[0,0,f.diaphragmZ+.1],silver,'Ultrasonic-IO '+id+' actual recessed static silver diaphragm');
 const cone=cylinder(frame,1.0,.65,[0,0,3.225],silver,'Ultrasonic-IO '+id+' static central diaphragm boss',.45);
 const guard=[],span=Math.floor(f.innerRadiusMm/f.guardPitchMm);
 for(let i=-span;i<=span;i++){
  const at=i*f.guardPitchMm,length=2*Math.sqrt(f.guardAnchorRadiusMm**2-at**2);
  guard.push(mesh(frame,new THREE.BoxGeometry(length,f.guardWidthMm,f.guardDepthMm),screen,[0,at,f.guardZ],'Ultrasonic-IO '+id+' real open grid horizontal rib '+i));
  guard.push(mesh(frame,new THREE.BoxGeometry(f.guardWidthMm,length,f.guardDepthMm),screen,[at,0,f.guardZ+.025],'Ultrasonic-IO '+id+' real open grid vertical rib '+i));
 }
 const terminals=[];for(const sign of[-1,1])terminals.push(cylinder(frame,.26,1.8,[sign*4.6,0,-1.0],tin,'Ultrasonic-IO '+id+' actual can PCB solder terminal'));
 return{id,frame,housing,floor,support,supports,diaphragm,cone,guard,terminals};
}
function grove(host){
 const frame=new THREE.Group();frame.name='Ultrasonic-IO actual black HY2.0-4P receiving socket';frame.position.fromArray(spec.grove.position);frame.quaternion.copy(portQuaternion('bottom'));host.body.add(frame);
 const plastic=materials.plastic(spec.grove.color,{roughness:.7}),metal=materials.metal(0xbcb49a),box=(s,p,n,m=plastic)=>mesh(frame,new THREE.BoxGeometry(...s),m,p,'Ultrasonic-IO Grove '+n),rails=[];
 for(const sign of[-1,1]){rails.push(box([.65,5.9,4.4],[sign*4.675,-2.85,.4],'actual full side rail'));rails.push(box([1.1,5.9,.65],[sign*4.1,-2.85,2.275],'actual top retaining rail'));box([.7,1.2,.7],[sign*3.85,-1.1,1.95],'locking shoulder');}
 const floor=box([8.7,5.9,.65],[0,-2.85,-1.475],'physical socket floor'),rear=box([8.7,.65,3.75],[0,-5.475,.075],'actual deep dielectric rear'),bridge=box([4.8,1,.45],[0,-2.5,2.375],'actual locking bridge'),contacts=[],tails=[];
 for(let i=0;i<4;i++){contacts.push(box([.42,4.1,.42],[(i-1.5)*2,-2.85,.05],'real recessed male contact '+(i+1),metal));tails.push(box([.42,.42,1.45],[(i-1.5)*2,-5.1,-1.125],'actual fixed PCB solder terminal '+(i+1),metal));}
 const port=host.add(new Port({id:'grove',label:'PORT.B I/O · physical GND/5V/TRIG/ECHO',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:spec.grove.pins.map((name,i)=>({n:i+1,name})),meta:{role:'visual-connector',face:'bottom',scope:'Own GPIO product-photo labels andfour real metal contacts/cable pose only.No pulse timing,distance,soundwave,power/electrical orfirmware behavior.'}}));return{frame,rails,floor,rear,bridge,contacts,tails,port};
}
function fixing(host){const s=new THREE.Shape();s.absarc(0,0,1.6,0,tau,false);const h=new THREE.Path();for(let i=0;i<6;i++){const a=-i*tau/6,x=Math.cos(a)*.65,y=Math.sin(a)*.65;i?h.lineTo(x,y):h.moveTo(x,y);}h.closePath();s.holes.push(h);const metal=materials.metal(0xabb5a7,{roughness:.4}),head=solid(host.body,s,.5,[0,-16,-4.47],metal,'Ultrasonic-IO actual rear retaining hex head'),floor=cylinder(host.body,.66,.1,[0,-16,-3.92],metal,'Ultrasonic-IO physical recessed screw hex floor'),shank=cylinder(host.body,.65,6.0,[0,-16,-.87],metal,'Ultrasonic-IO retained single fixing shaft');return{head,floor,shank};}
export function buildUltrasonicIO(host,{rearCover=true}={}){
 if(typeof rearCover!=='boolean')throw new TypeError('rearCover must be boolean');
 const parts=addCadParts(host,data.filter(p=>rearCover||p.role==='front'),{shell:materials.plastic(0xe8eae4,{roughness:.83})}),pcb=board(host),carriers=spec.transducers.map(s=>acousticCarrier(host,s)),socket=grove(host),screw=rearCover?fixing(host):null,s=spec.labels.back;
 const film=rearCover?slab(host.body,...s.size,.04,.06,s.position,materials.plastic(0xe5e5e5,{roughness:.86}),[],0):null;if(film){film.name='Ultrasonic-IO real rear adhesive body-label substrate';film.userData={role:'physical-label-substrate',face:'back'};}
 host.ultrasonicIOAssembly={parts,pcb,carriers,socket,screw,film,rearCover};host.unitStickers=addStickers(host);
}
