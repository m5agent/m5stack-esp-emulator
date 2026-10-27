import * as THREE from 'three';
import {Module,Component,materials} from '../../core/index.js';
import {mesh} from '../../modeling/parts.js';
import {mergeGeometries} from 'three/addons/utils/BufferGeometryUtils.js';
import {printedArtwork} from '../../modeling/artwork.js';
import {spec} from './dimensions.js';
const label=new URL('./reference-redraw-mq5.png',import.meta.url).href;
function circleHole(s,x,z,r){const h=new THREE.Path();h.absarc(x,z,r,0,Math.PI*2,false);s.holes.push(h);}
function disk(parent,name,outer,inner,depth,y,mat,holes=[]){const s=new THREE.Shape();s.absarc(0,0,outer,0,Math.PI*2,false);if(inner)circleHole(s,0,0,inner);for(const p of holes)circleHole(s,p.x,p.z,p.r);return mesh(parent,new THREE.ExtrudeGeometry(s,{depth,bevelEnabled:false,curveSegments:80}).rotateX(Math.PI/2),mat,[0,y,0],name);}
function segment(a,b,r,sides=4){const av=new THREE.Vector3(...a),bv=new THREE.Vector3(...b),d=bv.clone().sub(av),g=new THREE.CylinderGeometry(r,r,d.length(),sides,1,false);g.applyQuaternion(new THREE.Quaternion().setFromUnitVectors(new THREE.Vector3(0,1,0),d.normalize()));g.translate(...av.add(bv).multiplyScalar(.5).toArray());return g;}
function weave(parent,mat){
 const wires=[],r0=8.2,r1=6.75,start=5.25,end=15.85,around=144,levels=40;
 // Separate round metal wires with genuine air between them. No opaque cone,
 // black face, alpha texture or photograph stands in for the protective mesh.
 for(let k=0;k<around;k++){const t=k/around*Math.PI*2,pts=[];for(let j=0;j<=8;j++){const u=j/8,r=THREE.MathUtils.lerp(r0,r1,u)+Math.sin(j*Math.PI/2+k*Math.PI)*.022;pts.push(new THREE.Vector3(Math.cos(t)*r,THREE.MathUtils.lerp(start,end,u),Math.sin(t)*r));}wires.push(new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts),8,.026,3,false));}
 for(let j=0;j<=levels;j++){const u=j/levels,y=THREE.MathUtils.lerp(start,end,u),r=THREE.MathUtils.lerp(r0,r1,u),g=new THREE.TorusGeometry(r,.027,3,144);g.rotateX(Math.PI/2);g.translate(0,y,0);wires.push(g);}
 for(const axis of[0,1])for(let i=-22;i<=22;i++){const offset=i*.295,span=Math.sqrt(Math.max(0,r1*r1-offset*offset));if(span<.1)continue;wires.push(segment(axis?[offset,end,-span]:[-span,end,offset],axis?[offset,end,span]:[span,end,offset],.026,4));}
 const combined=mergeGeometries(wires,false);for(const g of wires)g.dispose();const net=mesh(parent,combined,mat,[0,0,0],'MQ-5 actual woven metal protection mesh and open lattice crown');net.userData={role:'physical-metal-mesh',wireCount:around+levels+1+90,airGaps:true,texture:false,inferred:'Protective mesh wire pitch/gauge and weave phase estimated from exact MQ-5 own photo; not a manufacturing filter specification'};return net;
}
/** Only the documented detachable round-pin MQ-5 can, not the fixed adapter. */
export class MQ5Cartridge extends Module{
 static meta={id:'m5stack.unit.mq.mq5-cartridge',name:'Unit MQ supplied MQ-5 round-pin cartridge',sku:'U199 accessory',connector:'mq5-six-pin'};
 build(){
  const tin=materials.metal(0xb7bab7,{roughness:.44}),meshMetal=materials.metal(0xa5a9a5,{roughness:.68}),dark=materials.plastic(0x34302c,{roughness:.86}),ceramic=materials.plastic(0xd9d8cc,{roughness:.92});
  const frame=new THREE.Group();frame.name='MQ-5 detachable round-pin sensor can';this.body.add(frame);
  const base=disk(frame,'MQ-5 black bakelite six-pin seal',9.05,0,1.05,1.1,dark,spec.mq5.pins.map(p=>({...p,r:.52}))),pins=[];
  for(const p of spec.mq5.pins){const pin=mesh(frame,new THREE.CylinderGeometry(.5,.5,7.5,24),tin,[p.x,-3.75,p.z],`MQ-5 round contact pin${p.n}`);pin.userData={role:'physical-contact',pin:p.n};pins.push(pin);}
  const flange=disk(frame,'MQ-5 real silver flange ring',9.5,7.8,3.15,4.2,tin),rolledRim=disk(frame,'MQ-5 rolled retaining lip',8.6,7.75,.6,5.35,tin);
  const lower=disk(frame,'MQ-5 concealed insulating support',7.7,0,.8,2.4,dark),ceramicTube=disk(frame,'MQ-5 internal ceramic sensing tube',1.65,.9,5.5,10.7,ceramic);
  const leads=[];for(const p of spec.mq5.pins)leads.push(mesh(frame,segment([p.x,1.5,p.z],[Math.sign(p.x)*1.1,7.5,p.z*.25],.12,6),tin,[0,0,0],`MQ-5 concealed internal electrode lead${p.n}`));
  const coilPts=[];for(let i=0;i<=120;i++){const t=i/120;coilPts.push(new THREE.Vector3(Math.cos(t*Math.PI*16)*.56,5.9+t*4.1,Math.sin(t*Math.PI*16)*.56));}
  const heater=mesh(frame,new THREE.TubeGeometry(new THREE.CatmullRomCurve3(coilPts),120,.08,5,false),materials.metal(0x6b6a62,{roughness:.78}),[0,0,0],'MQ-5 unpowered internal heater wire');
  const net=weave(frame,meshMetal),crown=disk(frame,'MQ-5 small rolled top mesh rim',6.86,6.68,.12,15.91,tin);
  const barrel=mesh(frame,new THREE.CylinderGeometry(8.5,9.5,1.3,128,1,false),tin,[0,4.65,0],'MQ-5 solid marked collar');
  const artwork=printedArtwork(this,{target:barrel,url:label,size:[5.2,1.1],position:[0,4.65,9.2],depth:1.5,artworkKind:'reference-redraw',name:'MQ-5 own product collar lettering'})??[];
  this.add(new Component({id:'appearance',label:'MQ-5 passive visual cartridge',meta:{role:'visual-anchor',scope:'Physical appearance and removable round-pin mechanical attachment only. No gas value, heater, alarm, ADC, temperature, concentration, electrical behavior or firmware.'}}));
  frame.userData={role:'physical-sensor-cartridge',model:'MQ-5',source:'Exact U199 official photo08 and own linked MQ-5 datasheet structure',inferred:'Mesh gauge/pitch, internal leads, ceramic/coil layout and insertion clearance reconstructed for appearance only'};
  this.mq5Assembly={frame,base,pins,flange,rolledRim,lower,ceramicTube,leads,heater,net,crown,barrel,artwork};
 }
}
