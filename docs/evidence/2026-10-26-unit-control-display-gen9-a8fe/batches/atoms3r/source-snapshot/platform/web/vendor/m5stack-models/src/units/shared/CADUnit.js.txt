import * as THREE from 'three';
import {Device,Module,Component,materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {grove,slab,mesh,disc,screw} from '../../modeling/parts.js';
import {artwork} from '../../modeling/artwork.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
export function makeUnit(spec,data,details){
 function build(host){
  addCadParts(host,data,{shell:materials.plastic(0xe0e3dc,{roughness:.8}),lens:materials.plastic(0xd3d7d1,{roughness:.47,transparent:true,opacity:.72})});
  // The actual circuit board closes assembly/sensor windows. Keep mounting holes
  // clear through the complete assembly, including the hidden board layer.
  const pcb=slab(host.body,22.8,spec.size[1]-1.6,.8,3.7,[0,0,spec.id==='encoder'?-4.8:.2],materials.plastic(0x2b493b,{roughness:.9}),[-8,8].map(cx=>({w:6.2,h:6.2,r:3.1,cx,cy:spec.mountY})),.05);
  pcb.name='Unit PCB';
  grove(host,{position:spec.grove.position,face:'bottom',w:10,h:5,color:spec.grove.color??0x1b2225});
  host.add(new Component({id:'sensor',label:spec.name,meta:{role:'visual-anchor',scope:'no-sensor-behavior'}}));
  screw(host.body,[0,spec.mountY,spec.label.position[2]+.01],'back',1.4);
  if(spec.artwork)null;
  details(host);
 }
 class Model extends Device{static meta={id:'m5stack.unit.'+spec.id,name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap:spec.keymap??{}};build(){build(this);}}
 class GroveModule extends Module{
  static meta={id:'m5stack.unit.'+spec.id+'.grove',name:spec.name,connector:'grove'};
  build(options={}){buildGroveModuleAssembly(this,build,options);
  }
 }
 return {Model,GroveModule};
}
export function cylinder(parent,r,height,position,material){return mesh(parent,new THREE.CylinderGeometry(r,r,height,64).rotateX(Math.PI/2),material,position);}
export function knob(parent,{x=0,y=7,z=4,r=5.4,h=13,cap=0x168bbc}){
 const group=new THREE.Group();group.position.set(x,y,z);parent.add(group);const black=materials.plastic(0x171c1e,{roughness:.85});
 cylinder(group,r,h,[0,0,h/2],black);
 for(let i=0;i<24;i++){const a=i*Math.PI/12;const rib=slab(group,.55,.8,h-.8,.2,[r*Math.cos(a),r*Math.sin(a),.3],black,[],.08);rib.rotation.z=a;}
 disc(group,r-.7,[0,0,h+.02],materials.plastic(cap,{roughness:.62}));slab(group,.55,r*.8,.03,.1,[0,r*.4,h+.04],black,[],.008);return group;
}
export function can(parent,{x=0,y=7,z=4,r=4.5,h=.6,lens=0x243044}){
 cylinder(parent,r,h,[x,y,z+h/2],materials.metal(0x9fa5a5,{roughness:.4}));disc(parent,r*.69,[x,y,z+h+.015],materials.glossy(lens,{roughness:.2}));
}
