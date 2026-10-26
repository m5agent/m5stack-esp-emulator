import *as THREE from'three';
import{Component,Button,materials}from'../../core/index.js';
import{addCadParts}from'../../modeling/cad.js';
import{mesh,slab,screw}from'../../modeling/parts.js';
import{spec}from'./dimensions.js';import data from'./geometry-data.js';import{addStickers}from'./stickers.js';import{grove,terminal}from'./connectors.js';

/** Hidden PCB controls have no pointer target through the assembled shell. */
class InspectionSlide extends Button{get interactive(){return this.meta.assemblyInspection===true;}onPointerDown(info){if(this.interactive)super.onPointerDown(info);}onPointerUp(info){if(this.interactive)super.onPointerUp(info);}onPointerCancel(info){if(this.interactive)super.onPointerCancel(info);}}
function circuit(host){
 const x=10.3,y=-16,r=3.7,dx=x-8,dy=Math.sqrt(r*r-dx*dx),a=Math.acos(dx/r),s=new THREE.Shape();
 s.moveTo(-5.4,-26.5);s.lineTo(-7,-26.5);s.lineTo(-x,-23.2);s.lineTo(-x,y-dy);s.absarc(-8,y,r,Math.PI+a,Math.PI-a,false);s.lineTo(-x,24.6);s.lineTo(-8,26.4);s.lineTo(8,26.4);s.lineTo(x,24.6);s.lineTo(x,y+dy);s.absarc(8,y,r,a,Math.PI*2-a,false);s.lineTo(x,-23.2);s.lineTo(7,-26.5);s.lineTo(5.4,-26.5);s.lineTo(5.4,-20.4);s.lineTo(-5.4,-20.4);s.closePath();
 const bore=new THREE.Path();bore.absarc(0,y,2.05,0,Math.PI*2,false);s.holes.push(bore);
 for(let i=0;i<5;i++){const hole=new THREE.Path();hole.absarc(9,5-i*2.54,.4,0,Math.PI*2,false);s.holes.push(hole);}
 const pcb=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:40}),materials.plastic(0x236843,{roughness:.9}),[0,0,-1.5],'HBridge v1.1 PCB with physical mounting scallops and retaining bore');pcb.userData={role:'physical-pcb',scope:'Photo-reconstructed own v1.1 outline/plane; no copper/electrical simulation'};
 const dark=materials.plastic(0x242827,{roughness:.84}),metal=materials.metal(0xb4b6a7,{roughness:.45}),ceramic=materials.plastic(0xab956d,{roughness:.87}),parts=[];
 const part=(name,w,h,d,p,mat=dark)=>{const m=slab(host.body,w,h,d,.1,p,mat,[],.025);m.name='HBridge v1.1 '+name;parts.push(m);return m;};
 const ic=(name,w,h,d,p,pins,pitch)=>{const body=part(name,w,h,d,p);for(const side of[-1,1]){const count=pins===3?(side<0?2:1):pins/2;for(let i=0;i<count;i++)mesh(host.body,new THREE.BoxGeometry(.65,.35,.15),metal,[p[0]+side*(w/2+.28),p[1]+(i-(count-1)/2)*pitch,p[2]+.25],'HBridge v1.1 '+name+' soldered lead');}return body;};
 const stm32=ic('U3 STM32F030F4P6 TSSOP20 controller package',4.4,6.5,1.1,[3.6,-8,-.7],20,.65),driver=ic('U4 RZ7899 SOP8 motor-driver physical package',5,5.8,1.45,[4.8,19,-.7],8,1.27),ina=ic('U5 INA199A1DCKR SC70 current-monitor package',2,2.1,.8,[1.7,12,-.7],6,.65),dcdc=ic('U1 SY8303AIC physical buck-controller package',3,3,1.05,[-5.4,19.2,-.7],8,.65),ldo=ic('U2 HX6306P332MR physical LDO package',1.7,2.9,1,[-7.8,4.6,-.7],3,.95),ao=ic('Q1 AO3401A package',1.7,2.9,1,[-7.1,1,-.7],3,.95),q2=ic('Q2 DTC143ZCA package',1.6,2.5,.9,[-4.3,.1,-.7],3,.8),tl=ic('U6 TL432 reference package',1.7,2.6,.9,[.1,8.4,-.7],3,.8);
 const inductor=part('L1 shielded6.8uH power inductor',6,6,2.3,[-4.7,11.6,-.7],materials.plastic(0x737b70,{roughness:.72}));for(const side of[-1,1])part('L1 metal end',.65,5,.45,[-4.7+side*3,11.6,-.7],metal);
 const shunt=part('R4 10mΩ1206 physical shunt',3.2,1.6,.7,[4.4,12.5,-.7]);for(const side of[-1,1])part('R4 shunt end',.5,1.7,.8,[4.4+side*1.65,12.5,-.7],metal);
 const fuse=part('F1 3A physical fuse package',3.1,1.6,.65,[7.8,9.1,-.7],ceramic);for(const side of[-1,1])part('F1 end',.55,1.7,.75,[7.8+side*1.6,9.1,-.7],metal);
 const bulk=[];for(let i=0;i<3;i++){bulk.push(part(`C${11+i}22µF low-profile physical capacitor`,3.9,2.7,1.75,[7.5,16-i*3.4,-.7],ceramic));for(const side of[-1,1])part('bulk capacitor termination',.45,2.8,1.8,[7.5+side*1.9,16-i*3.4,-.7],metal);}
 for(const[x,y,w,h]of[[-8.2,20.1,2,3],[-8,7.6,1,1.5],[-3.3,5.2,1.8,2.6],[-.3,14,1.5,2.4],[2.5,15.4,1.6,2.5],[-.3,-.7,1,1.5],[7.9,-5,1.8,2.6],[8,-10.5,1,1.5],[-7,-12.5,1,1.5],[-4.5,-12.3,1,1.5],[-1.6,-12.1,1,1.5]])part('own v1.1 fixed passive or protection package',w,h,.7,[x,y,-.7],ceramic);
 const swd=[];for(let i=0;i<5;i++){const ring=mesh(host.body,new THREE.TorusGeometry(.55,.16,8,24),metal,[9,5-i*2.54,-.68],'HBridge v1.1 SWD physical solder-pad ring');swd.push(ring);}
 return{pcb,parts,stm32,driver,ina,dcdc,ldo,ao,q2,tl,inductor,shunt,fuse,bulk,swd};
}
function controls(host,inspection){
 const dark=materials.plastic(0x202522,{roughness:.83}),metal=materials.metal(0xb0b5ac,{roughness:.46}),cream=materials.plastic(0xe7e5c4,{roughness:.66});
 const base=slab(host.body,6,3.4,1.5,.18,[4.65,3.8,-.7],dark,[],.025);base.name='HBridge v1.1 S1 TA-3539S-A1 fixed source selector body';
 for(const side of[-1,1])for(const x of[2.65,4.65,6.65])mesh(host.body,new THREE.BoxGeometry(.45,.75,.2),metal,[x,3.8+side*1.85,-.45],'HBridge v1.1 source-selector fixed solder lead');
 const cover=slab(host.body,6.2,3.6,.38,.15,[4.65,3.8,.8],metal,[{w:3.5,h:1.65,r:.15,cx:0,cy:0}],.025);cover.name='HBridge v1.1 source selector real slotted metal cover';
 const cap=new THREE.Group();cap.name='HBridge v1.1 source moving thumb';mesh(cap,new THREE.BoxGeometry(1.5,1.4,1.5),dark,[0,0,0],'HBridge v1.1 source thumb');for(let i=0;i<4;i++)mesh(cap,new THREE.BoxGeometry(.13,1.35,.13),materials.plastic(0x4a4e47),[(i-1.5)*.3,0,.78],'HBridge v1.1 source thumb grip');
 const source=host.add(new InspectionSlide({id:'source',label:'S1 · DCDC5V / external6–12V physical slide',mesh:cap,position:spec.selector.position,axis:spec.selector.axis,travel:spec.selector.travelMm,latching:true,meta:{role:'visual-control',assemblyInspection:inspection,mechanism:'retained-slide',positions:spec.selector.positions,sourceLabels:spec.selector.sourceLabels,electricalMapping:'Not asserted; visual index only',detentsMm:[0,1.5],travelSource:'Native own board photo estimate; actual throw/installed plane not measured',scope:'PCB actuator shape and input intent only. Closed shell has no pointer access; covers:false exposes it. No power switching, motor, voltage, current, speed, protection or electrical/firmware behavior'}}));
 const dipBody=slab(host.body,8.8,6.2,1.6,.15,[-4.7,-8,-.7],dark,spec.address.positions.map(([x])=>({w:.95,h:2.6,r:.08,cx:x+4.7,cy:0})),.025);dipBody.name='HBridge v1.1 SW1 own four-position DIP package with real slider recesses';
 for(const side of[-1,1])for(const[x]of spec.address.positions)mesh(host.body,new THREE.BoxGeometry(.55,.75,.2),metal,[x,-8+side*3.25,-.45],'HBridge v1.1 DIP fixed solder lead');
 const address=spec.address.positions.map((position,i)=>{const thumb=slab(new THREE.Group(),.72,1.05,.7,.06,[0,0,0],cream,[],.01);thumb.name=`HBridge v1.1 SW1 ${i+1} retained cream actuator`;const control=host.add(new InspectionSlide({id:`address-${i+1}`,label:`SW1.${i+1} physical DIP position`,mesh:thumb,position,axis:spec.address.axis,travel:spec.address.travelMm,latching:true,meta:{role:'visual-control',assemblyInspection:inspection,mechanism:'retained-slide',positions:['rest','shifted'],detentsMm:[0,1.1],travelSource:'Own bare-board photo estimate, no switch datasheet/production-fit throw',scope:'Stable physical DIP slider shape and input intent only. Closed shell has no pointer access; no I2C address algorithm, GPIO, boot, continuity, voltage, motor or firmware behavior'}}));return control;});
 if(!inspection)for(const c of[source,...address])c.cap.traverse(o=>{delete o.userData.component;});
 return{base,cover,source,dipBody,address};
}
export function buildHBridge(host,options={}){
 const parts=addCadParts(host,data,{shell:materials.plastic(0xe8e9e3,{roughness:.78})}),pcb=circuit(host),input=grove(host),output=terminal(host),actuators=controls(host,options.covers===false);const fixing=screw(host.body,[0,-16,-3.98],'back',1.35);
 host.add(new Component({id:'sensor',label:'HBridge v1.1 passive appearance anchor',meta:{role:'visual-anchor',scope:'No motor, sensor values, PWM, power selection, voltage, current, I2C, address, capacitor charge/discharge, polarity, protection, firmware or electrical simulation'}}));
 host.hbridgeAssembly={parts,pcb,input,terminal:output,controls:actuators,fixing,artwork:[]};host.hbridgeAssembly.artwork=addStickers(host);
 if(options.covers===false){for(const shell of Object.values(parts))shell.visible=false;for(const layer of host.hbridgeAssembly.artwork)layer.visible=false;}
}
