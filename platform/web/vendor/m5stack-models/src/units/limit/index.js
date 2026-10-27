import {addStickers} from './stickers.js';
import * as THREE from 'three';
import {Device,Module,Component,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {grove,slab,mesh,screw} from '../../modeling/parts.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {LeverButton} from './LeverButton.js';
import {spec} from './dimensions.js';
import data from './geometry-data.js';

function buildLimit(host){
 addCadParts(host,data,{shell:materials.plastic(0xe4e6df,{roughness:.76})});
 const green=materials.plastic(0x245343,{roughness:.88}),teal=materials.plastic(0x006b65,{roughness:.63});
 const black=materials.plastic(0x191e20,{roughness:.71}),silver=materials.metal(0xb6b9b6,{roughness:.39});
 // The circuit board follows the shell, with real bores and a Grove insertion
 // clearance; it must not make a solid plate across the connector opening.
 const boardShape=new THREE.Shape(),x=11.3,y=15.1,r=2.6,n=5.2;
 boardShape.moveTo(-x+r,-y);boardShape.lineTo(-n,-y);boardShape.lineTo(-n,-8.8);boardShape.lineTo(n,-8.8);boardShape.lineTo(n,-y);boardShape.lineTo(x-r,-y);
 boardShape.absarc(x-r,-y+r,r,-Math.PI/2,0);boardShape.lineTo(x,y-r);boardShape.absarc(x-r,y-r,r,0,Math.PI/2);
 boardShape.lineTo(-x+r,y);boardShape.absarc(-x+r,y-r,r,Math.PI/2,Math.PI);boardShape.lineTo(-x,-y+r);boardShape.absarc(-x+r,-y+r,r,Math.PI,Math.PI*1.5);
 for(const cx of [-8,8]){const bore=new THREE.Path();bore.absarc(cx,spec.mountY,3.1,0,Math.PI*2,true);boardShape.holes.push(bore);}
 mesh(host.body,new THREE.ExtrudeGeometry(boardShape,{depth:.8,bevelEnabled:false,curveSegments:24}),green,[0,0,-2.7],'Limit circuit board with open mounting bores');
 const body=slab(host.body,...spec.switch.size,.45,[...spec.switch.position.slice(0,2),-spec.switch.size[2]/2],teal,[],.09);body.name='KW4A microswitch body';
 // Shallow molded package seam and pins remain inside the physical shell.
 const seam=slab(host.body,19.8,.22,6.25,.08,[0,10.75,-3.125],materials.plastic(0x07544f,{roughness:.85}),[],.02);seam.name='KW4A package seam';
 for(const px of [-6,0,6])mesh(host.body,new THREE.BoxGeometry(.5,2.5,.35),silver,[px,4.6,-2.95],'Microswitch terminal');
 const connector=grove(host,{position:spec.grove.position,face:'bottom',w:10,h:5,color:spec.grove.color});
 // This exposed U145 connector has an open top and a short latch, as shown in
 // the official front photograph. Retain the shared mating frame and contacts.
 const cover=connector.children.find(o=>o.geometry?.parameters?.height===.8&&o.position.y>0);
 if(!cover)throw new Error('Limit open-top Grove cover was not found');
 const connectorPlastic=cover.material;cover.removeFromParent();cover.geometry.dispose();
 for(const x of [-3.85,3.85])mesh(connector,new THREE.BoxGeometry(.9,.8,5.8),connectorPlastic,[x,2.1,-2.9],'Limit Grove open-top rail');
 mesh(connector,new THREE.BoxGeometry(3.4,.65,1.05),connectorPlastic,[0,1.1,-3.5],'Limit Grove latch bridge');
 screw(host.body,[0,-4,-4.73],'back',1.4);
 const lever=spec.lever,angle=lever.restAngleDeg*Math.PI/180;
 const plungerTop=lever.pivot[1]+lever.contactX*Math.sin(angle);
 const plunger=mesh(host.body,new THREE.CylinderGeometry(.9,.95,1.2,32),black,[lever.pivot[0]+lever.contactX*Math.cos(angle),plungerTop-.6,0],'Limit moving actuator plunger');
 const collar=mesh(host.body,new THREE.CylinderGeometry(1.12,1.12,.12,32),black,[plunger.position.x,15.85,0],'Limit plunger collar');
 collar.userData.role='fixed-switch-subassembly';
 // Hinge pin stays fixed. Only the bent spring lever rotates about this axis.
 for(const z of [-2.55,2.55])mesh(host.body,new THREE.BoxGeometry(1.5,.85,1.0),black,[lever.pivot[0],16.2,z],'Limit fixed hinge support');
 const axle=new THREE.CylinderGeometry(.48,.48,5.5,32).rotateX(Math.PI/2);
 mesh(host.body,axle,silver,[...lever.pivot],'Limit fixed lever hinge');
 const cap=new THREE.Group();cap.name='Limit articulated 16 mm metal lever';
 mesh(cap,new THREE.BoxGeometry(lever.length,lever.thickness,lever.width),silver.clone(),[lever.length/2,lever.thickness/2,0],'Limit metal lever blade');
 mesh(cap,new THREE.BoxGeometry(lever.thickness,.9,lever.width),silver.clone(),[lever.thickness/2,-.45,0],'Limit bent lever root');
 cap.userData={role:'physical-actuator-cap',lengthMm:lever.length,hingeAxis:lever.axis,source:'official-dimension-and-photo-derived'};
 const control=host.add(new LeverButton({id:'press',label:'Limit switch lever',mesh:cap,position:lever.pivot,lever,plunger,longPressMs:800,meta:{role:'visual-control',actuation:'momentary',motion:'hinged-lever',visualMotion:'lever',angularTravelDeg:8,rangeEvidence:lever.evidence,part:'KW4A (S)',scope:'no-electrical-state'}}));
 host.add(new Component({id:'sensor',label:'Limit switch visual anchor',meta:{role:'visual-anchor',scope:'no-sensor-behavior'}}));
 host.limitMechanism={control,plunger,collar};
 addStickers(host);
}
export class Model extends Device{
 static meta={id:'m5stack.unit.limit',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:{Space:'press'}};
 build(){buildLimit(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.limit.grove',name:spec.name,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,buildLimit,options);}
}
export {LeverButton};
export default Model;
