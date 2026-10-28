import * as THREE from 'three';
import {Port,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
const tau=Math.PI*2;
function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:48}),material,position,name);}
function bore(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,tau,false);shape.holes.push(h);}

function board(host){
 const s=new THREE.Shape(),edge=10.5,r=3.3,a=Math.acos((edge-8)/r),dy=Math.sqrt(r*r-(edge-8)**2),cy=-4;
 s.moveTo(-edge,14.5);s.lineTo(edge,14.5);s.lineTo(edge,cy+dy);s.absarc(8,cy,r,a,tau-a,false);s.lineTo(edge,-14.5);s.lineTo(5.4,-14.5);s.lineTo(5.4,-9.7);s.lineTo(-5.4,-9.7);s.lineTo(-5.4,-14.5);s.lineTo(-edge,-14.5);s.lineTo(-edge,cy-dy);s.absarc(-8,cy,r,Math.PI+a,Math.PI-a,false);s.lineTo(-edge,14.5);s.closePath();bore(s,0,-4,1.2);
 const green=materials.plastic(0x256443,{roughness:.9}),dark=materials.plastic(0x252925,{roughness:.86}),metal=materials.metal(0xb9b9a6),ceramic=materials.plastic(0xb5a27f),pcb=solid(host.body,s,.8,[0,0,-1.15],green,'Grove2Grove shaped PCB with real fixing bore,mounting reliefs and black-socket notch');pcb.userData={role:'physical-pcb',inferred:true};
 const packages={},packagePads={};
 for(const cfg of[{id:'ht7533',name:'HT7533',position:[-3.1,3],size:[4.5,2.5,1.4],pads:[[-1.65,-1.5],[0,-1.5],[1.65,-1.5]]},{id:'ina199',name:'INA199A1DCKR',position:[2.3,3],size:[2,1.25,.9],pads:[[-1.2,-.45],[-1.2,0],[-1.2,.45],[1.2,-.45],[1.2,0],[1.2,.45]]},{id:'sgm2553',name:'SGM2553D',position:[2.3,7],size:[2,2,.75],pads:[[-.93,-.6],[-.93,0],[-.93,.6],[.93,-.6],[.93,0],[.93,.6],[0,0]]},{id:'tl432',name:'TL432',position:[-3,7.3],size:[2.9,1.3,1],pads:[[-1.2,-.8],[1.2,-.8],[0,.8]]}]){
  const q=slab(host.body,cfg.size[0],cfg.size[1],cfg.size[2],.08,[...cfg.position,-.25],dark,[],.01);q.name='Grove2Grove actual '+cfg.name+' fixed package envelope';q.userData={role:'physical-ic',inferredInstallation:true,inferredPackageEnvelope:true};packages[cfg.id]=q;
  packagePads[cfg.id]=cfg.pads.map(([x,y],i)=>{const exposed=cfg.id==='sgm2553'&&i===6;return mesh(host.body,new THREE.BoxGeometry(exposed?1.1:cfg.id==='ina199'?.55:.35,exposed?1.1:cfg.id==='ht7533'?.6:cfg.id==='tl432'?.5:.22,.1),metal,[cfg.position[0]+x,cfg.position[1]+y,-.3],'Grove2Grove '+cfg.name+' physical '+(exposed?'exposed pad':'terminal '+(i+1)));});
 }
 const passives=[];for(const[name,x,y,w,h]of[['R1',0,10,1.1,.65],['R2',-3,10,1.1,.65],['R3',0,-8,3.2,1.6],['R5',4.7,6.3,1.1,.65],['R6',4.7,8.3,1.1,.65],['C1',-5.8,4,1.1,.65],['C2',2.3,10,1.1,.65],['C3',4.8,2,1.1,.65],['C4',4.8,10,1.1,.65]]){const q=slab(host.body,w,h,.45,.035,[x,y,-.25],name[0]==='R'?dark:ceramic,[],.005);q.name='Grove2Grove populated '+name+(name==='R3'?' 1206 shunt':'')+' fixed schematic envelope';passives.push(q);for(const sign of[-1,1])mesh(host.body,new THREE.BoxGeometry(.17,h,.1),metal,[x+sign*(w/2-.07),y,-.3],'Grove2Grove '+name+' physical termination');}
 return {pcb,packages,packagePads,passives};
}

function boardSocket(host,id){
 const cfg=spec[id],frame=new THREE.Group();frame.name='Grove2Grove '+id+' actual '+(id==='grove'?'black':'white')+' HY2.0-4P board-pin socket';frame.position.fromArray(cfg.position);frame.quaternion.copy(portQuaternion(cfg.face));host.body.add(frame);
 const plastic=materials.plastic(cfg.color,{roughness:.68}),metal=materials.metal(0xbdb59c),box=(size,position,name,mat=plastic)=>mesh(frame,new THREE.BoxGeometry(...size),mat,position,'Grove2Grove '+id+' '+name);
 const rails=[];for(const sign of[-1,1]){rails.push(box([.65,5.9,4.4],[sign*4.675,-2.85,.4],'full open side rail'));rails.push(box([1.1,5.9,.65],[sign*4.1,-2.85,2.275],'top retaining rail'));box([.7,1.2,.7],[sign*3.85,-1.1,1.95],'actual locking shoulder');}
 const floor=box([8.7,5.9,.65],[0,-2.85,-1.475],'actual socket floor'),rear=box([8.7,.65,3.75],[0,-5.475,.075],'recessed dielectric rear'),bridge=box([4.8,1,.45],[0,-2.5,2.375],'real fixed retaining bridge'),contacts=[],tails=[];
 for(let i=0;i<4;i++){contacts.push(box([.42,4.1,.42],[(i-1.5)*2,-2.85,.05],'real recessed male contact '+(i+1),metal));tails.push(box([.42,.42,1.45],[(i-1.5)*2,-5.1,-1.125],'retained PCB terminal '+(i+1),metal));}
 const port=host.add(new Port({id,label:cfg.label,connector:'grove',position:cfg.position,quaternion:portQuaternion(cfg.face),hitSize:[10,1,4.4],pins:cfg.pins.map((name,i)=>({n:i+1,name})),meta:{role:'visual-connector',face:cfg.face,physicalFamily:'HY2.0-4P open board-pin socket',scope:'Mechanical receiving socket with four actual male pins;ordinary four-core cable plug accepted.No fixed cableendplug,current measurement,power switching,signal orprotocol/electrical routing'}}));return {frame,rails,floor,rear,bridge,contacts,tails,port};
}

function adhesive(host){
 const material=materials.plastic(0xdee1dc,{roughness:.89}),front=slab(host.body,...spec.labels.front.size,.04,.12,[0,9.7,3.800001],material,[],0),back=slab(host.body,...spec.labels.back.size,.04,.65,[0,7.7,-3.84],material,[],0);front.name='Grove2Grove independent narrow front arrow-label adhesive film';back.name='Grove2Grove independent rear PORT.B title adhesive film';for(const[face,q]of Object.entries({front,back}))q.userData={role:'physical-label-substrate',face};return{front,back};
}
function fixing(host){
 const material=materials.metal(0xacb2ad,{roughness:.4}),s=new THREE.Shape();s.absarc(0,0,1.55,0,tau,false);const h=new THREE.Path();for(let i=0;i<6;i++){const a=-i*Math.PI/3,x=Math.cos(a)*.67,y=Math.sin(a)*.67;i?h.lineTo(x,y):h.moveTo(x,y);}h.closePath();s.holes.push(h);const head=solid(host.body,s,.5,[0,-4,-3.97],material,'Grove2Grove actual fixed hex-socket retaining head'),floor=mesh(host.body,new THREE.CylinderGeometry(.68,.68,.1,6).rotateX(Math.PI/2),material,[0,-4,-3.42],'Grove2Grove recessed retaining hex floor'),shank=mesh(host.body,new THREE.CylinderGeometry(.7,.7,6.1,32).rotateX(Math.PI/2),material,[0,-4,-.42],'Grove2Grove fixed retaining shaft');return{head,floor,shank};
}
export function buildGroveToGrove(host){const parts=addCadParts(host,data,{shell:materials.plastic(0xe7e9e3,{roughness:.8})}),electronics=board(host),sockets={grove:boardSocket(host,'grove'),in:boardSocket(host,'in'),out:boardSocket(host,'out')},films=adhesive(host),screw=fixing(host);host.groveToGroveAssembly={parts,electronics,sockets,films,screw};host.unitStickers=addStickers(host);}
