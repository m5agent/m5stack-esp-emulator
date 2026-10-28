import * as THREE from 'three';
import {Button,Component,Port,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
const tau=Math.PI*2;
function bore(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,tau,false);shape.holes.push(h);}
function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:48}),material,position,name);}
function electronics(host){
 const shape=new THREE.Shape(),edge=10.5,r=3.4,a=Math.acos((edge-8)/r),dy=Math.sqrt(r*r-(edge-8)**2);
 shape.moveTo(-edge,10.5);shape.lineTo(edge,10.5);shape.lineTo(edge,dy);shape.absarc(8,0,r,a,tau-a,false);shape.lineTo(edge,-10.5);shape.lineTo(5.5,-10.5);shape.lineTo(5.5,-6.5);shape.lineTo(-5.5,-6.5);shape.lineTo(-5.5,-10.5);shape.lineTo(-edge,-10.5);shape.lineTo(-edge,-dy);shape.absarc(-8,0,r,Math.PI+a,Math.PI-a,false);shape.lineTo(-edge,10.5);shape.closePath();bore(shape,0,0,1.1);
 const metal=materials.metal(0xb8b6a0),dark=materials.plastic(0x242821,{roughness:.87}),ceramic=materials.plastic(0xb4a07e),pcb=solid(host.body,shape,.8,[0,0,-1.8],materials.plastic(0x24613f,{roughness:.9}),'DoF6 own shaped PCB with retaining bore,mount reliefs and Grove notch');pcb.userData={role:'physical-pcb',inferred:true};
 const bmi270=slab(host.body,2.5,3,.75,.08,spec.bmi270.position,dark,[],.01);bmi270.name='DoF6 actual BMI270 LGA14 package';
 const bmiPads=[];for(const sign of[-1,1]){for(let i=0;i<4;i++)bmiPads.push(mesh(host.body,new THREE.BoxGeometry(.3,.25,.08),metal,[2.5+sign*1.1,4+(i-1.5)*.5,-.96],'DoF6 BMI270 actual LGA pad'));for(let i=0;i<3;i++)bmiPads.push(mesh(host.body,new THREE.BoxGeometry(.25,.3,.08),metal,[2.5+(i-1)*.5,4+sign*1.35,-.96],'DoF6 BMI270 actual LGA pad'));}
 const ldo=slab(host.body,1.3,2.8,.7,.06,[-3,7.5,-.9],dark,[],.005);ldo.name='DoF6 actual U1 ME6206A33M3G LDO envelope';const ldoLeads=[];for(const[sign,dy]of[[-1,-.7],[-1,.7],[1,0]])ldoLeads.push(mesh(host.body,new THREE.BoxGeometry(.35,.24,.1),metal,[-3+sign*1.3*.45,7.5+dy,-.95],'DoF6 U1 retained metal termination'));
 const passives=[],passiveTerminations=[];for(const[n,x,y]of[['R1',-4.5,6],['R2',4.4,5.8],['R3',-4.2,8.7],['C1',-7,-5],['C2',-7,-7],['C3',-4,-4.4],['C5',3,2],['C6',4.8,3]]){const q=slab(host.body,1.1,.65,.45,.04,[x,y,-.92],n[0]==='R'?dark:ceramic,[],.005);q.name='DoF6 populated '+n+' fixed own-schematic envelope';passives.push(q);for(const sign of[-1,1])passiveTerminations.push(mesh(host.body,new THREE.BoxGeometry(.17,.65,.08),metal,[x+sign*.48,y,-.96],'DoF6 passive physical termination'));}
 const grovePads=[];for(let i=0;i<4;i++)grovePads.push(mesh(host.body,new THREE.BoxGeometry(.85,.85,.025),metal,[(i-1.5)*2,-6.1,-.9875],'DoF6 Grove PCB metal solder pad '+(i+1)));
 return {pcb,bmi270,bmiPads,ldo,ldoLeads,passives,passiveTerminations,grovePads};
}
function groveSocket(host){
 const frame=new THREE.Group();frame.name='DoF6 actual red HY2.0-4P receiving socket';frame.position.fromArray(spec.grove.position);frame.quaternion.copy(portQuaternion('bottom'));host.body.add(frame);
 const plastic=materials.plastic(spec.grove.color,{roughness:.7}),metal=materials.metal(0xbcb49a),box=(s,p,n,m=plastic)=>mesh(frame,new THREE.BoxGeometry(...s),m,p,'DoF6 Grove '+n),rails=[];
 for(const sign of[-1,1]){rails.push(box([.65,5.9,4.4],[sign*4.675,-2.85,.4],'actual full side rail'));rails.push(box([1.1,5.9,.65],[sign*4.1,-2.85,2.275],'actual top retaining rail'));box([.7,1.2,.7],[sign*3.85,-1.1,1.95],'locking shoulder');}
 const floor=box([8.7,5.9,.65],[0,-2.85,-1.475],'physical socket floor'),rear=box([8.7,.65,3.75],[0,-5.475,.075],'actual recessed dielectric rear'),bridge=box([4.8,1,.45],[0,-2.5,2.375],'actual retaining bridge'),contacts=[],tails=[];
 for(let i=0;i<4;i++){const x=(i-1.5)*2;contacts.push(box([.42,4.1,.42],[x,-2.85,.05],'real recessed male contact '+(i+1),metal));const tail=new THREE.Group();tail.name='DoF6 Grove retained connected PCB tail '+(i+1);frame.add(tail);mesh(tail,new THREE.BoxGeometry(.42,1.2,.42),metal,[x,-5.4,.05],'DoF6 Grove connected contact extension '+(i+1));mesh(tail,new THREE.BoxGeometry(.42,.42,2.15),metal,[x,-5.8,-1.025],'DoF6 Grove real PCB solder leg '+(i+1));tails.push(tail);}
 const port=host.add(new Port({id:'grove',label:'PORT.A · documentary I2C labels',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:spec.grove.pins.map((name,i)=>({n:i+1,name,color:['black','red','yellow','white'][i]})),meta:{role:'visual-connector',face:'bottom',scope:'Mechanical HY2.0-4P socket,four actual contacts,cable pose and printed pin labels only;no I2C,address,voltage,power or sensor behavior'}}));return {frame,rails,floor,rear,bridge,contacts,tails,port};
}
function addressSwitch(host,position){
 const dark=materials.plastic(0x20251f,{roughness:.87}),metal=materials.metal(0xacb3a9),cream=materials.plastic(0xd9d0ac,{roughness:.7}),profile=roundedRect(6.6,2.2,.12);profile.holes.push(roundedRect(4.6,1.35,.07,{path:new THREE.Path(),clockwise:true}));
 const retainer=mesh(host.body,new THREE.ExtrudeGeometry(profile,{depth:1.55,bevelEnabled:false,curveSegments:32}).rotateX(Math.PI/2),metal,[0,11.15,.1],'DoF6 SW1 actual fixed open metal retainer');
 const base=slab(host.body,6.35,.75,2.2,.08,[0,9.35,-1],dark,[],.01);base.name='DoF6 SW1 actual fixed switch body behind native slot';
 const moving=new THREE.Group();moving.name='DoF6 actual retained cream SW1 thumb and stem';const thumb=slab(moving,.95,1.2,1.25,.1,[0,0,-.625],cream,[],.01);thumb.name='DoF6 actual exposed cream SW1 thumb';const stem=mesh(moving,new THREE.BoxGeometry(.55,1.3,.8),dark.clone(),[0,-.8,0],'DoF6 SW1 retained moving stem');
 const control=host.add(new Button({id:'address',label:'SW1 stable physical 0 / 1 detent',mesh:moving,position:spec.address.position,axis:spec.address.axis,travel:spec.address.travelMm,latching:true,longPressMs:0,meta:{role:'visual-control',mechanism:'two-detent slide',surfaceFace:'top',detents:[0,1],travelSource:'Exact U228 own photograph10 proves exposed cream thumb and fixed retainer in native top7.22×3mm slot;1.8mm throw is inferred visual travel,not manufacturer rating.',scope:'Stable physical detent and input intent only;release/cancel retain position,setPosition(0|1) resets explicitly.No BMI270 address computation,I2C routing,sensor values,power or firmware behavior'}}));delete stem.userData.component;control.setPosition(position,{immediate:true});
 const terminals=[];for(const x of[-2.5,0,2.5])terminals.push(mesh(host.body,new THREE.BoxGeometry(.4,.65,.1),metal,[x,8.8,-.95],'DoF6 SW1 actual fixed solder terminal'));return {retainer,base,moving,thumb,stem,control,terminals};
}
function fixing(host){
 const metal=materials.metal(0xabb1ab,{roughness:.4}),shape=new THREE.Shape();shape.absarc(0,0,1.6,0,tau,false);const h=new THREE.Path();for(let i=0;i<6;i++){const a=-i*Math.PI/3,x=Math.cos(a)*.67,y=Math.sin(a)*.67;i?h.lineTo(x,y):h.moveTo(x,y);}h.closePath();shape.holes.push(h);
 const head=solid(host.body,shape,.5,[0,0,-3.97],metal,'DoF6 actual fixed hex-socket retaining head'),floor=mesh(host.body,new THREE.CylinderGeometry(.68,.68,.1,6).rotateX(Math.PI/2),metal,[0,0,-3.42],'DoF6 retaining screw recessed hex floor'),shank=mesh(host.body,new THREE.CylinderGeometry(.7,.7,6.5,32).rotateX(Math.PI/2),metal,[0,0,-.22],'DoF6 retained fixed screw shaft');return {head,floor,shank};
}
function films(host){
 const material=materials.plastic(0xe6e7df,{roughness:.86}),front=slab(host.body,...spec.labels.front.size,.04,.55,[0,7.3,3.8],material,[],0),back=slab(host.body,...spec.labels.back.size,.04,.03,[0,7.3,-3.84],material,[],0),axisShape=new THREE.Shape();axisShape.absarc(0,0,3.1,0,tau,false);const axis=solid(host.body,axisShape,.04,[0,0,4],material,'DoF6 independent physical circular XYZ adhesive film');front.name='DoF6 independent physical front BMI270 title film';back.name='DoF6 independent physical rear PORT.A film';for(const[face,q]of Object.entries({front,axis,back}))q.userData={role:'physical-label-substrate',face};return {front,axis,back};
}
export function buildDof6(host,{addressPosition=0}={}){
 if(addressPosition!==0&&addressPosition!==1)throw new RangeError('addressPosition must be 0 or 1');
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe6e9e2,{roughness:.8})}),board=electronics(host),input=groveSocket(host),address=addressSwitch(host,addressPosition),screw=fixing(host),labels=films(host),bmi270=host.add(new Component({id:'bmi270',label:'DoF6 passive physical BMI270 package frame',position:spec.bmi270.position,meta:{role:'visual-anchor',scope:spec.bmi270.scope}}));
 host.dof6Assembly={parts,board,input,address,screw,labels,bmi270};host.unitStickers=addStickers(host);
}
