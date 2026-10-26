import * as THREE from 'three';
import {Device, Module, Component, Port, materials} from '../../core/index.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {mesh, slab, ring, connector, mountingDetail, backLabel, transducer, notchedSlab,shellSkirt,unitPcb} from './parts.js';
function buildUnit(host,spec){
 const groups={};for(const k of ['rear','front','sensor','connector','pcb']){groups[k]=new THREE.Group();groups[k].name=k;host.body.add(groups[k]);}host.parts=groups;
 const white=materials.plastic(0xededE8,{roughness:.67,clearcoat:.025});
 const hy=-spec.h/2+12;
 const mount=[-8,8].map(cx=>({w:5,h:5,r:2.5,cx,cy:hy}));
 const vents=[];
 if(spec.key==='env')for(let col=0;col<9;col++){const n=col%2?5:4;for(let row=0;row<n;row++)vents.push({w:.95,h:1.9,r:.47,cx:-8+2*col,cy:(col%2?13:11.6)-row*2.8});}
 slab(groups.rear,24,spec.h,3.1,4,[0,0,-4],white,[...mount,{w:3.8,h:3.8,r:1.9,cx:0,cy:hy}],.32,'rear-shell');
 shellSkirt(groups.front,spec,white);
 notchedSlab(groups.front,spec,[...mount,...vents],white);
 for(const x of [-8,8])ring(groups.front,3.15,2.5,3.8,[x,hy,-1.0],white,'mounting-post');
 // Thin seam is the interface of two independently bevelled shells; no painted perimeter.
 for(const x of [-8,8]){mountingDetail(groups.front,x,hy,4.015);mountingDetail(groups.rear,x,hy,-4.02,true);}
 unitPcb(groups.pcb,spec);
 connector(groups.connector,spec.h,spec.key==='pir',{height:spec.key==='sonic'?4.8:5.2});backLabel(groups.rear,spec);
 // Small interlocking clips visible on the side walls.
 for(const x of [-11.98,11.98])for(const y of [hy,spec.h/2-9]){
   const clip=mesh(groups.front,new THREE.BoxGeometry(.14,3,1.8),materials.plastic(0xd5d9d4),[x,y,-.2]);clip.name='shell-clip';
 }
 if(spec.key==='pir'){
   ring(groups.sensor,5.45,4.8,.3,[0,8,3.95],materials.plastic(0xd7dad5));
   const radius=(5.1**2+4.5**2)/(2*4.5), theta=Math.acos((radius-4.5)/radius);
   const lensGeo=new THREE.SphereGeometry(radius,40,12,0,Math.PI*2,0,theta).rotateX(Math.PI/2);
   mesh(groups.sensor,lensGeo,materials.plastic(0xe2e4dc,{roughness:.48,clearcoat:.15,flatShading:true}),[0,8,8.5-radius],'fresnel-lens');
   for(let i=1;i<=5;i++){const a=theta*i/6;const r=radius*Math.sin(a);const z=8.5-radius+radius*Math.cos(a);mesh(groups.sensor,new THREE.TorusGeometry(r,.022,4,64),materials.plastic(0xcdd2c8,{roughness:.6}),[0,8,z]);}
 }
 if(spec.key==='sonic'){transducer(groups.sensor,18);transducer(groups.sensor,-4);}
 const sensor=host.add(new Component({id:'sensor',label:spec.subtitle,meta:{chip:spec.chip,role:'visual-anchor'}}));
 groups.sensor.traverse(o=>{if(o.isMesh)sensor.hit(o);});
 const pinNames=spec.key==='pir'?['GND','5V','NC','OUT']:['GND','5V','SDA','SCL'];
 host.add(new Port({id:'grove',label:'HY2.0-4P · Grove',connector:'grove',position:[0,-spec.h/2,1.4],rotation:[0,0,Math.PI],hitSize:[10,1,5.2],pins:pinNames.map((name,i)=>({n:i+1,name})),meta:{protocol:spec.protocol,face:'bottom',role:'visual-connector'}}));
 return groups;
}
export class UnitDevice extends Device {
 build(){buildUnit(this,this.constructor.spec);}
 setExplode(amount){this.ensureBuilt();this.parts.rear.position.z=-amount*8;this.parts.front.position.z=amount*5;this.parts.sensor.position.z=amount*13;this.parts.connector.position.y=-amount*5;this.requestRender();}
 update(dt,t){const anim=super.update(dt,t);if(this.autoRotate){this.root.rotateY(dt*.3);return true;}return anim;}
}
export function createGroveModule(spec){return class extends Module {
 static meta={id:`${spec.id}.grove`,name:`Unit · ${spec.name}`,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,host=>buildUnit(host,spec),options);
 }
};}
