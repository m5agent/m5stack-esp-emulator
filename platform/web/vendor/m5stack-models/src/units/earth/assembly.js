import * as THREE from 'three';
import {Component,Port,VisualJoint,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,portQuaternion,screw} from '../../modeling/parts.js';
import {connector} from '../shared/parts.js';
import {spec} from './dimensions.js';
import {addStickers} from './stickers.js';
import data from './geometry-data.js';
const tau=Math.PI*2;
function bore(s,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,tau,false);s.holes.push(h);}
function extrusion(parent,shape,depth,z,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:40}),material,[0,0,z],name);}
function circuit(host){
 const s=new THREE.Shape();s.moveTo(-8,-2.0);s.lineTo(8,-2.0);s.lineTo(10.3,-4.2);s.lineTo(10.3,-15.85);s.lineTo(8,-15.85);s.absarc(8,-20.15,4.3,Math.PI/2,Math.PI*1.5,false);s.lineTo(10.3,-24.45);s.lineTo(10.3,-28.5);s.lineTo(8.3,-30.5);s.lineTo(5.4,-30.5);s.lineTo(5.4,-24.4);s.lineTo(-5.4,-24.4);s.lineTo(-5.4,-30.5);s.lineTo(-8.3,-30.5);s.lineTo(-10.3,-28.5);s.lineTo(-10.3,-24.45);s.lineTo(-8,-24.45);s.absarc(-8,-20.15,4.3,Math.PI*1.5,Math.PI*2.5,false);s.lineTo(-10.3,-15.85);s.lineTo(-10.3,-4.2);s.closePath();bore(s,0,-20.15,1.9);for(const x of[-3,-1,1,3])bore(s,x,-24.9,.32);
 const pcb=extrusion(host.body,s,.8,-1,materials.plastic(0x173f2f,{roughness:.92}),'Earth physical circuit PCB with true mounting/Grove solder drillings');pcb.userData={role:'physical-pcb',scope:'Concealed visual board; outline/installed plane reconstructed around unchanged native bosses'};
 const dark=materials.plastic(0x252b27,{roughness:.86}),metal=materials.metal(0xb4b6a9,{roughness:.5}),ceramic=materials.plastic(0xad9d72,{roughness:.9}),parts=[];
 const comparator=mesh(host.body,new THREE.BoxGeometry(4.9,3.9,1.5),dark,[0,-14.8,.55],'Earth U1 LM393DR2G physical comparator package');parts.push(comparator);
 for(const side of[-1,1])for(let i=0;i<4;i++)parts.push(mesh(host.body,new THREE.BoxGeometry(.5,1.4,.16),metal,[(i-1.5)*1.27,-14.8+side*2.3,-.12],'Earth LM393 stationary solder terminal'));
 parts.push(mesh(host.body,new THREE.BoxGeometry(2.9,1.6,1.0),dark,[-6.9,-10.3,.3],'Earth HT7533 physical regulator package'));
 for(const dx of[-.95,0,.95])parts.push(mesh(host.body,new THREE.BoxGeometry(.35,.7,.12),metal,[-6.9+dx,-11.35,-.14],'Earth regulator solder terminal'));
 for(const[x,y]of[[6.8,-10.5],[6.8,-13.4],[-6.8,-5.4],[6.7,-5.4],[-3,-18],[3,-18],[6.3,-26.5],[-6.3,-26.5]]){
  parts.push(mesh(host.body,new THREE.BoxGeometry(1.5,.85,.55),ceramic,[x,y,.075],'Earth resistor/capacitor physical package'));
  for(const dx of[-.62,.62])parts.push(mesh(host.body,new THREE.BoxGeometry(.28,.88,.57),metal,[x+dx,y,.075],'Earth passive metal termination'));
 }
 const probeTabs=[];for(const x of[-4,4]){probeTabs.push(mesh(host.body,new THREE.BoxGeometry(2.6,3,.2),metal,[x,-2.8,.1],'Earth internal electrode contact tab'));probeTabs.push(mesh(host.body,new THREE.BoxGeometry(.7,2.8,1.8),metal,[x,-2.8,.9],'Earth vertical electrode-to-circuit connection'));}
 return{pcb,parts,comparator,probeTabs};
}
function forkShape({gold=false,side=null}={}){
 const s=new THREE.Shape();if(side===null){s.moveTo(-6,-3);s.lineTo(6,-3);s.lineTo(6,28.65);s.lineTo(4.35,32.15);s.lineTo(3.7,32.15);s.lineTo(2.05,28.65);s.lineTo(2.05,3.95);s.absarc(0,3.95,2.05,0,-Math.PI,true);s.lineTo(-2.05,28.65);s.lineTo(-3.7,32.15);s.lineTo(-4.35,32.15);s.lineTo(-6,28.65);s.closePath();}
 else{const x=side*4.025;s.moveTo(x-1.975,4.15);s.lineTo(x+1.975,4.15);s.lineTo(x+1.975,28.65);s.lineTo(x+.325,32.15);s.lineTo(x-.325,32.15);s.lineTo(x-1.975,28.65);s.closePath();}
 const holes=[];for(const sign of[-1,1]){if(side!==null&&sign!==side)continue;for(let i=0;i<9;i++)for(const dx of[-1,1])holes.push([sign*4.025+dx,7.35+i*2.55,.42]);holes.push([sign*4.025,30.2,.42]);}for(const[x,y,r]of holes)bore(s,x,y,r);return{s,holes};
}
function probe(host){
 const shape=forkShape(),board=extrusion(host.body,shape.s,1,1.2,materials.plastic(0x171b20,{roughness:.84}),'Earth real twin-tine probe PCB with 38 through holes');board.userData={role:'physical-probe-pcb',holes:38,scope:'Dimensions/photo constrained shape, genuine through holes; no measured conductive material or sensing function'};
 const electrodeMaterial=materials.metal(0xb99b43,{roughness:.56,metalness:.62}),electrodes=[];
 for(const side of[-1,1])for(const z of[1.174,2.2]){const{ s }=forkShape({gold:true,side});electrodes.push(extrusion(host.body,s,.026,z,electrodeMaterial,'Earth gold-colored physical electrode face with matching true drillings'));}
 const holes=shape.holes,barrels=[];const ringMaterial=materials.metal(0xa49052,{roughness:.6});for(const[x,y,r]of holes){const ann=new THREE.Shape();ann.absarc(x,y,r+.045,0,tau,false);bore(ann,x,y,r);barrels.push(extrusion(host.body,ann,1.052,1.174,ringMaterial,'Earth probe through-hole metal-colored wall'));}
 return{board,electrodes,holes,barrels};
}
function threshold(host){
 const[x,y,z]=spec.trim.axis,blue=materials.plastic(0x0767b5,{roughness:.69}),metal=materials.metal(0x90999e,{roughness:.46}),darkMetal=materials.metal(0x4c565a,{roughness:.64});
 const shape=new THREE.Shape();shape.moveTo(x-3.25,y-3.25);shape.lineTo(x+3.25,y-3.25);shape.lineTo(x+3.25,y+3.25);shape.lineTo(x-3.25,y+3.25);shape.closePath();bore(shape,x,y,1.85);
 const fixed=extrusion(host.body,shape,3.7,.08,blue,'Earth fixed blue R3 10K trimmer housing with true rotor bore');
 const base=mesh(host.body,new THREE.BoxGeometry(6.5,6.5,.3),blue,[x,y,-.07],'Earth fixed potentiometer base');
 const rotor=new THREE.Group();rotor.name='Earth physically slotted metallic threshold trim head';host.body.add(rotor);
 const shaft=mesh(rotor,new THREE.CylinderGeometry(1.55,1.55,2.5,64).rotateX(Math.PI/2),metal,[x,y,2.23],'Earth moving trimmer rotor/shaft');
 const lower=mesh(rotor,new THREE.CylinderGeometry(1.62,1.62,.16,64).rotateX(Math.PI/2),darkMetal,[x,y,3.52],'Earth recessed solid floor of cross-slot head');
 const top=new THREE.Shape();top.absarc(x,y,1.62,0,tau,false);const cross=new THREE.Path();for(const[dx,dy]of[[-.32,-1.24],[.32,-1.24],[.32,-.32],[1.24,-.32],[1.24,.32],[.32,.32],[.32,1.24],[-.32,1.24],[-.32,.32],[-1.24,.32],[-1.24,-.32],[-.32,-.32]]){if(cross.currentPoint.x===0&&cross.currentPoint.y===0)cross.moveTo(x+dx,y+dy);else cross.lineTo(x+dx,y+dy);}cross.closePath();top.holes.push(cross);
 const slotted=extrusion(rotor,top,.26,3.6,metal,'Earth metallic head with actual recessed cross slot');
 const joint=host.add(new VisualJoint({id:'trim',label:'Earth exposed threshold adjustment head',position:spec.trim.axis,axis:[0,0,1],meta:{visualRangeDeg:spec.trim.visualRangeDeg,mechanicalLimitsConfirmed:false,part:'R3 10K RPot',axisEvidence:'Centre of original square front access opening and exposed official-photo trim head',scope:'External visual angle only, including intermediate poses; no RPM or press. No supplied mechanical stop or electrical zero/direction. No threshold, resistance, comparator, ADC, moisture or input event is inferred.'}}));joint.adopt(rotor);
 const terminals=[];for(const dx of[-2.5,0,2.5])terminals.push(mesh(host.body,new THREE.BoxGeometry(.6,.6,1.3),metal,[x+dx,y,-.57],'Earth fixed potentiometer solder terminal'));
 return{joint,rotor,shaft,lower,slotted,fixed,base,terminals};
}
export function buildEarth(host){
 const native=addCadParts(host,data,{shell:materials.plastic(0xe8eae5,{roughness:.77})}),physicalCircuit=circuit(host),physicalProbe=probe(host),trim=threshold(host);
 const socket=connector(host.body,64.3,true,{height:5.2});socket.name='Earth black open-top HY2.0-4P';
 const port=host.add(new Port({id:'grove',label:'PORT.B · analog/digital outputs',connector:'grove',position:spec.grove.position,quaternion:portQuaternion('bottom'),hitSize:[10,1,5.2],pins:[{n:1,name:'GND',color:'black'},{n:2,name:'5V',color:'red'},{n:3,name:'D.OUT',color:'yellow'},{n:4,name:'A.OUT',color:'white'}],pinGrid:{cols:4,rows:1,pitch:2,center:[0,.2],order:col=>col+1},meta:{role:'visual-connector',face:'bottom',scope:'Physical attachment, pin labels and four-wire cable pose only; no ADC, comparator, threshold, moisture, power or electrical behavior'}}));
 const fixing=screw(host.body,[0,-20.15,-3.97],'back',1.4),shank=mesh(host.body,new THREE.CylinderGeometry(.65,.65,1.5,32).rotateX(Math.PI/2),materials.metal(0x929997),[0,-20.15,-2.7],'Earth rear fastening screw shank');
 const sensor=host.add(new Component({id:'sensor',label:'Earth twin-electrode physical anchor',position:[0,14,1.7],meta:{role:'visual-anchor',part:'U2 EARTH_PIN',scope:'Passive visual anchor only; no moisture, calibrated data, conductivity, corrosion, ADC, comparator, threshold, firmware or electrical behavior'}}));
 const stickers=addStickers(host,native['Earth complete native assembled shell']);host.earthAssembly={native,circuit:physicalCircuit,probe:physicalProbe,trim,socket,port,fixing,shank,sensor,stickers};
}
