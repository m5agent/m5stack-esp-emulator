import * as THREE from 'three';
import {Button,Component,Port,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,FACE,portQuaternion} from '../../modeling/parts.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';
import {addStickers} from './stickers.js';
const tau=Math.PI*2;
function bore(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,tau,false);shape.holes.push(h);}
function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:48}),material,position,name);}

function electronics(host){
 const s=new THREE.Shape(),edge=10.5,r=3.4,a=Math.acos((edge-8)/r),dy=Math.sqrt(r*r-(edge-8)**2);
 s.moveTo(-edge,10.5);s.lineTo(edge,10.5);s.lineTo(edge,dy);s.absarc(8,0,r,a,tau-a,false);s.lineTo(edge,-10.5);s.lineTo(5.5,-10.5);s.lineTo(5.5,-6.5);s.lineTo(-5.5,-6.5);s.lineTo(-5.5,-10.5);s.lineTo(-edge,-10.5);s.lineTo(-edge,-dy);s.absarc(-8,0,r,Math.PI+a,Math.PI-a,false);s.lineTo(-edge,10.5);s.closePath();bore(s,0,0,1.1);
 const metal=materials.metal(0xb8b6a0),dark=materials.plastic(0x242821,{roughness:.87}),green=materials.plastic(0x24613f,{roughness:.9}),ceramic=materials.plastic(0xb4a07e),pcb=solid(host.body,s,.8,[0,0,-1.8],green,'DoF10 shaped PCB with actual retaining bore,open mounting reliefs and Grove notch');pcb.userData={role:'physical-pcb',inferred:true};
 const bmi270=slab(host.body,2.5,3,.75,.08,spec.packages.bmi270.position,dark,[],.01);bmi270.name='DoF10 actual BMI270 LGA14 package';
 const bmiPads=[];for(const sign of[-1,1]){
  for(let i=0;i<4;i++)bmiPads.push(mesh(host.body,new THREE.BoxGeometry(.3,.25,.08),metal,[2.5+sign*1.1,4+(i-1.5)*.5,-.96],'DoF10 BMI270 retained LGA pad'));
  for(let i=0;i<3;i++)bmiPads.push(mesh(host.body,new THREE.BoxGeometry(.25,.3,.08),metal,[2.5+(i-1)*.5,4+sign*1.35,-.96],'DoF10 BMI270 retained LGA pad'));
 }
 const bmm350=slab(host.body,1.28,1.28,.306,.035,spec.packages.bmm350.position,dark,[],.005);bmm350.name='DoF10 actual BMM350 WLCSP9 package';
 const bmmBalls=[];for(const x of[-.4,0,.4])for(const y of[-.4,0,.4])bmmBalls.push(mesh(host.body,new THREE.SphereGeometry(.1345,20,14).scale(1,1,.097/.1345),metal,[-2.5+x,4+y,-.903],'DoF10 BMM350 real WLCSP solder ball'));
 const spaBase=slab(host.body,2,2.5,.67,.25,[0,7.5,-.92],dark,[],.005);spaBase.name='DoF10 actual SPA06-003 LGA8 pressure-sensor base';
 const capShape=roundedRect(2,2.5,.25);bore(capShape,-.3,.4,.15);const spaLid=solid(host.body,capShape,.2,[0,7.5,-.25],materials.metal(0xb2b6af,{roughness:.6}),'DoF10 SPA06-003 metal lid with real pressure access orifice');const pressureFloor=mesh(host.body,new THREE.CylinderGeometry(.16,.16,.05,24).rotateX(Math.PI/2),dark,[-.3,7.9,-.275],'DoF10 recessed non-emissive pressure-sensor cavity');
 const spaPads=[];for(const sign of[-1,1])for(let i=0;i<4;i++)spaPads.push(mesh(host.body,new THREE.BoxGeometry(.24,.28,.08),metal,[sign*.84,7.5+(i-1.5)*.5,-.96],'DoF10 SPA06-003 retained LGA pad'));
 const ldos=[];for(const[x,y,w,h,name]of[[-3,7.5,1.3,2.8,'ME6206A33M3G'],[3.7,7.8,1,1,'SSP7615-18DFR']]){const p=slab(host.body,w,h,.7,.06,[x,y,-.9],dark,[],.005);p.name='DoF10 fixed '+name+' LDO envelope';ldos.push(p);for(const[sign,dy]of(name==='ME6206A33M3G'?[[-1,-.7],[-1,.7],[1,0]]:[[-1,-.25],[-1,.25],[1,-.25],[1,.25]]))mesh(host.body,new THREE.BoxGeometry(.35,.24,.1),metal,[x+sign*w*.45,y+dy,-.95],'DoF10 LDO retained termination');}
 const passives=[];for(const[n,x,y]of[['R1',-4.5,6],['R2',4.4,5.8],['R3',-4.2,8.7],['R4',-2.5,2.5],['R5',-2.5,5.5],['C1',-7,-5],['C2',-7,-7],['C3',-4,-4.4],['C4',-2.3,6],['C5',3,2],['C6',4.8,3],['C7',-3.8,2],['C8',0,5],['C9',-1,2],['C10',5.4,8.8],['C11',6.3,6.5]]){const q=slab(host.body,1.1,.65,.45,.04,[x,y,-.92],n[0]==='R'?dark:ceramic,[],.005);q.name='DoF10 populated '+n+' fixed schematic envelope';passives.push(q);for(const sign of[-1,1])mesh(host.body,new THREE.BoxGeometry(.17,.65,.08),metal,[x+sign*.48,y,-.96],'DoF10 passive physical termination');}
 return {pcb,bmi270,bmiPads,bmm350,bmmBalls,spaBase,spaLid,pressureFloor,spaPads,ldos,passives};
}

function grove(host){
 const frame=new THREE.Group();frame.name='DoF10 actual red HY2.0-4P socket';frame.position.fromArray(spec.grove.position);frame.quaternion.copy(FACE.bottom);host.body.add(frame);const plastic=materials.plastic(spec.grove.color,{roughness:.67}),metal=materials.metal(0xb8b39d),box=(s,p,n,m=plastic)=>mesh(frame,new THREE.BoxGeometry(...s),m,p,'DoF10 Grove '+n),depth=6.3;
 for(const sign of[-1,1]){box([.65,5.2,depth],[sign*4.675,0,-depth/2],'side rail');box([.7,.6,3.2],[sign*3.85,2.3,-4.7],'guide rail');box([.6,.45,1.2],[sign*3.65,2.375,-1.8],'locking shoulder');}box([8.7,.65,depth],[0,-2.275,-depth/2],'floor');const rear=box([8.7,4.55,.65],[0,.325,-depth+.325],'real recessed dielectric rear');box([4.8,.45,2.3],[0,2.375,-4.5],'retaining bridge');const contacts=[];for(let i=0;i<4;i++){contacts.push(box([.42,.42,4.5],[(i-1.5)*2,.2,-3.6],'real contact '+(i+1),metal));box([.42,1.2,.42],[(i-1.5)*2,-2.6,-5.8],'retained solder leg '+(i+1),metal);}
 const port=host.add(new Port({id:'grove',label:'PORT.A · I2C documentary labels',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:['GND','5V','SDA','SCL'].map((name,i)=>({n:i+1,name,color:['black','red','yellow','white'][i]})),meta:{role:'visual-connector',face:'bottom',scope:'Mechanical HY2.0-4P family,four contacts,cable pose and documentary pin labels only;no I2C,address,voltage,power or sensor data behavior'}}));return {frame,rear,contacts,port};
}

function addressSwitch(host){
 const dark=materials.plastic(0x20251f,{roughness:.87}),metal=materials.metal(0xacb3a9),cream=materials.plastic(0xd9d0ac,{roughness:.7}),profile=roundedRect(6.6,2.2,.12);profile.holes.push(roundedRect(4.6,1.35,.07,{path:new THREE.Path(),clockwise:true}));
 const retainer=mesh(host.body,new THREE.ExtrudeGeometry(profile,{depth:1.55,bevelEnabled:false,curveSegments:32}).rotateX(Math.PI/2),metal,[0,11.15,.1],'DoF10 SW1 actual fixed open metal retainer');
 const base=slab(host.body,6.35,.75,2.2,.08,[0,9.35,-1],dark,[],.01);base.name='DoF10 SW1 actual fixed switch body behind native slot';
 const moving=new THREE.Group();moving.name='DoF10 real retained cream SW1 thumb and stem';const thumb=slab(moving,.95,1.2,1.25,.1,[0,0,-.625],cream,[],.01);thumb.name='DoF10 actual exposed cream SW1 thumb';const stem=mesh(moving,new THREE.BoxGeometry(.55,1.3,.8),dark,[0,-.8,0],'DoF10 SW1 retained moving stem');
 const control=host.add(new Button({id:'address',label:'SW1 stable physical 0 / 1 detent',mesh:moving,position:spec.address.position,axis:spec.address.axis,travel:spec.address.travelMm,latching:true,longPressMs:0,meta:{role:'visual-control',mechanism:'two-detent slide',surfaceFace:'top',detents:[0,1],travelSource:'Own source top7.22×3mm slot and exact switch note prove accessible side-to-side thumb;1.8mm visual throw is inferred,not rated switch travel.',scope:'Stable physical position and input intent only;cancel ends the press while retaining detent.Use setPosition(0|1) for exact neutral reset.No BMI270 address calculation,I2C routing,sensor values,power or firmware behavior'}}));
 const terminals=[];for(const x of[-2.5,0,2.5])terminals.push(mesh(host.body,new THREE.BoxGeometry(.4,.65,.1),metal,[x,8.8,-.95],'DoF10 SW1 actual retained solder terminal'));
 return {retainer,base,moving,thumb,stem,control,terminals};
}

function fixing(host){
 const metal=materials.metal(0xabb1ab,{roughness:.4}),s=new THREE.Shape();s.absarc(0,0,1.6,0,tau,false);const h=new THREE.Path();for(let i=0;i<6;i++){const a=-i*Math.PI/3,x=Math.cos(a)*.67,y=Math.sin(a)*.67;i?h.lineTo(x,y):h.moveTo(x,y);}h.closePath();s.holes.push(h);const head=solid(host.body,s,.5,[0,0,-3.97],metal,'DoF10 actual fixed hex-socket retaining head'),floor=mesh(host.body,new THREE.CylinderGeometry(.68,.68,.1,6).rotateX(Math.PI/2),metal,[0,0,-3.42],'DoF10 retaining screw recessed hex floor'),shank=mesh(host.body,new THREE.CylinderGeometry(.7,.7,6.5,32).rotateX(Math.PI/2),metal,[0,0,-.22],'DoF10 retained fixed screw shaft');return {head,floor,shank};
}

function films(host){
 const material=materials.plastic(0xe6e7df,{roughness:.86}),front=slab(host.body,...spec.labels.front.size,.04,.55,[0,7.3,3.8],material,[],0),back=slab(host.body,...spec.labels.back.size,.04,.03,[0,7.3,-3.84],material,[],0),axisShape=new THREE.Shape();axisShape.absarc(0,0,spec.labels.axis.size[0]/2,0,tau,false);const axis=solid(host.body,axisShape,.04,[0,0,4],material,'DoF10 independent real circular XYZ adhesive film');front.name='DoF10 independent real front title adhesive film';back.name='DoF10 independent real rear PORT.A adhesive film';for(const[face,q]of Object.entries({front,axis,back}))q.userData={role:'physical-label-substrate',face};return {front,axis,back};
}
export function buildDof10(host){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe6e9e2,{roughness:.8})}),board=electronics(host),input=grove(host),address=addressSwitch(host),screw=fixing(host),labels=films(host),sensor=host.add(new Component({id:'sensor',label:'DoF10 passive physical package frame',position:spec.sensor.position,meta:{role:'visual-anchor',scope:spec.sensor.scope}}));
 host.dof10Assembly={parts,board,input,address,screw,labels,sensor};host.unitStickers=addStickers(host);
}
