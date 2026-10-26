import * as THREE from 'three';
import {Device,Module,Component,Button,Led,materials} from '../../core/index.js';
import {VisualJoint} from '../../core/components/VisualJoint.js';
import {addCadParts} from '../../modeling/cad.js';
import {buildGroveModuleAssembly} from '../../modeling/grove-cable.js';
import {slab,mesh,grove,screw} from '../../modeling/parts.js';
import {roundedRect} from '../../core/geometry.js';
import {spec,CHANNELS} from './dimensions.js';
import data from './geometry-data.js';

function cylinder(parent,r,depth,position,material,name){
 return mesh(parent,new THREE.CylinderGeometry(r,r,depth,48).rotateX(Math.PI/2),material,position,name);
}
function board(host){
 const shape=new THREE.Shape(),x=9.9,y=60,bottom=60,r=2.2,n=5.6,bore=4.2,edgeOffset=x-8,dy=Math.sqrt(bore*bore-edgeOffset*edgeOffset),theta=Math.acos(edgeOffset/bore);
 shape.moveTo(-x+r,-bottom);shape.lineTo(-n,-bottom);shape.lineTo(-n,-55.1);shape.lineTo(n,-55.1);shape.lineTo(n,-bottom);shape.lineTo(x-r,-bottom);
 shape.absarc(x-r,-bottom+r,r,-Math.PI/2,0);shape.lineTo(x,spec.mountY-dy);
 // Open cutouts clear the full native mounting pillars, not just their bores.
 // The central back-shell reinforcing boss has its own complete clearance.
 shape.absarc(8,spec.mountY,bore,-theta,theta-Math.PI*2,true);
 shape.lineTo(x,y-r);shape.absarc(x-r,y-r,r,0,Math.PI/2);shape.lineTo(-x+r,y);shape.absarc(-x+r,y-r,r,Math.PI/2,Math.PI);
 shape.lineTo(-x,spec.mountY+dy);shape.absarc(-8,spec.mountY,bore,Math.PI-theta,-Math.PI+theta,true);shape.lineTo(-x,-bottom+r);shape.absarc(-x+r,-bottom+r,r,Math.PI,Math.PI*1.5);
 shape.holes.push(roundedRect(6.6,6.6,3.3,{cx:0,cy:spec.mountY,path:new THREE.Path(),clockwise:true}));
 mesh(host.body,new THREE.ExtrudeGeometry(shape,{depth:.8,bevelEnabled:false,curveSegments:24}),materials.plastic(0x233e31,{roughness:.92}),[0,0,-2.6],'8Encoder PCB with Grove and mounting clearances');
 // The backside MCU stays above the native recessed back wall; it is not a
 // block pushed through the shell to hide the untextured service opening.
 slab(host.body,7,7,.95,.35,[0,-24,-3.55],materials.plastic(0x1c2420,{roughness:.9}),[],.04).name='8Encoder concealed MCU package';
}
function capGeometry(number){
 const black=materials.plastic(0x151a19,{roughness:.63}),white=materials.plastic(0xe3e6df,{roughness:.39});
 const cap=new THREE.Group();cap.name=`CH${number} physical knob`;
 // A real underside shaft bore prevents the fixed shaft from intersecting a
 // solid cap; the bore is blind, ending well below the visible top surface.
 const profile=[[1.7,0],[4.85,0],[5,.35],[4.82,.85],[4.65,13.65],[4.32,14.3],[0,14.3],[0,6],[1.7,6],[1.7,0]].map(p=>new THREE.Vector2(...p));
 mesh(cap,new THREE.LatheGeometry(profile,96).rotateX(Math.PI/2),black,[0,0,0],`CH${number} bored knob body`);
 for(let i=0;i<20;i++){
  const a=i*Math.PI/10,points=[];
  for(const z of [1.05,13.3]){const center=z<2?4.75:4.59;for(const [radial,tangent]of [[-.12,-.18],[.18,-.18],[.18,.18],[-.12,.18]])points.push((center+radial)*Math.cos(a)-tangent*Math.sin(a),(center+radial)*Math.sin(a)+tangent*Math.cos(a),z);}
  const geometry=new THREE.BufferGeometry();geometry.setAttribute('position',new THREE.Float32BufferAttribute(points,3));geometry.setIndex([0,2,1,0,3,2,4,5,6,4,6,7,0,1,5,0,5,4,1,2,6,1,6,5,2,3,7,2,7,6,3,0,4,3,4,7]);geometry.computeVertexNormals();
  mesh(cap,geometry,black,[0,0,0],`CH${number} molded grip flute`);
 }
 // The white insert has a genuine open notch; it is geometry, not silkscreen.
 const radius=3.9,half=.62,delta=Math.asin(half/radius),shape=new THREE.Shape();
 shape.moveTo(half,-Math.sqrt(radius*radius-half*half));shape.absarc(0,0,radius,-Math.PI/2+delta,Math.PI*1.5-delta,false);shape.lineTo(-half,-2.65);shape.lineTo(half,-2.65);shape.closePath();
 mesh(cap,new THREE.ExtrudeGeometry(shape,{depth:.3,bevelEnabled:false,curveSegments:32}),white,[0,0,14.3],`CH${number} notched white top insert`);
 cap.userData={role:'physical-actuator-cap',channel:number,source:'official-U153-drawing-and-photo-derived',boreRadiusMm:1.7,boreDepthMm:6};
 return cap;
}
function channel(host,item){
 const {number,y}=item,black=materials.plastic(0x242c27,{roughness:.83}),metal=materials.metal(0x9ca7a2,{roughness:.48});
 slab(host.body,11.2,11.2,4.8,.6,[0,y,-1.8],black,[],.08).name=`CH${number} fixed encoder package`;
 slab(host.body,10.8,10.8,.55,.5,[0,y,3.02],metal,[],.04).name=`CH${number} fixed encoder metal cover`;
 cylinder(host.body,3.15,1.18,[0,y,4.16],metal,`CH${number} fixed shaft bushing`);
 cylinder(host.body,spec.knob.shaftRadius,5.8,[0,y,6.9],metal,`CH${number} fixed encoder shaft`);
 const press=host.add(new Button({id:item.press,label:`CH${number} knob press`,mesh:capGeometry(number),position:[0,y,spec.knob.baseZ],travel:spec.knob.pressTravel,axis:[0,0,-1],meta:{role:'visual-control',channel:number,visualMotion:'linear',travelEvidence:'0.35 mm visual travel estimate; rated EC11A pretravel/overtravel unconfirmed',scope:'no-switch-state-or-encoder-count'}}));
 // Register the child before the adopting parent so each mesh is disposed once.
 const rotation=host.add(new VisualJoint({id:item.rotation,label:`CH${number} knob rotation`,position:[0,y,spec.knob.baseZ],axis:[0,0,1],continuous:true,meta:{channel:number,axisEvidence:'Official U153 EC11A rotary encoder; cap axis normal to front shell',demoRpmMax:60,scope:'no-quadrature-or-numeric-value'}}));
 rotation.adopt(press.object3d);
 return {press,rotation};
}
function light(host,{number,y}){
 const pipe=new THREE.Mesh(new THREE.BoxGeometry(spec.led.w,spec.led.h,spec.led.depth),materials.plastic(0x8f9b91,{roughness:.62}));pipe.position.z=-spec.led.depth/2;pipe.name=`RGB${number} recessed physical light pipe`;
 const led=host.add(new Led({id:'rgb-'+number,label:number<9?`CH${number} external RGB`:'Switch external RGB',mesh:pipe,position:[spec.led.x,y,spec.led.z],radius:.45,glowSize:3,lensColor:0x8f9b91,meta:{role:'externally-driven-visual',visualLocation:number<9?'CH'+number:'switch',mapping:'Physical location only; not the schematic U1-U9 chain order',scope:'no-automatic-key-or-power-response'}}));
 return led;
}
function slide(host){
 const dark=materials.plastic(0x111713,{roughness:.86});
 slab(host.body,7,4,5,.4,[0,59,-1.5],dark,[],.05).name='8Encoder fixed slide-switch package';
 slab(host.body,5.9,2.9,.6,.2,[0,59,4.3],dark,[{w:4.5,h:1.6,r:.12}],.025).name='8Encoder slide-switch slotted carrier';
 mesh(host.body,new THREE.BoxGeometry(4.5,1.6,.2),dark,[0,59,4.15],'8Encoder recessed slide-switch floor');
 const cap=new THREE.Group();cap.name='8Encoder stable slide-switch cap';
 slab(cap,1.2,1.1,1.5,.12,[0,0,0],materials.plastic(0x151c18,{roughness:.7}),[],.035).name='8Encoder slide-switch physical thumb';
 for(const x of [-.3,0,.3])mesh(cap,new THREE.BoxGeometry(.09,1,.12),materials.plastic(0x354139,{roughness:.9}),[x,0,1.51],'Slide-switch grip ridge');
 return host.add(new Button({id:'switch',label:'8Encoder stable slide switch',mesh:cap,position:[-1.1,59,4.45],axis:[1,0,0],travel:spec.slide.travel,latching:true,meta:{role:'visual-control',visualMotion:'linear',mechanism:'slide',detents:[0,1],positionEvidence:'Official U153 front photo and SS12D07L4B schematic; 2.2 mm visual detent spacing estimate',scope:'no-electrical-truth-table-or-power-behavior'}}));
}
function connector(host){
 const body=grove(host,{...spec.grove,color:0xa92323});body.name='8Encoder red HY2.0-4P socket';
 // Preserve the shared mating frame and metal pins; the photographed U153
 // connector has an open top and a short latch rather than a solid top plate.
 const cover=body.children.find(o=>o.geometry?.parameters?.height===.8&&o.position.y>0);
 if(!cover)throw new Error('8Encoder open-top Grove cover was not found');
 const plastic=cover.material;cover.removeFromParent();cover.geometry.dispose();
 for(const x of [-3.85,3.85])mesh(body,new THREE.BoxGeometry(.9,.8,spec.grove.depth),plastic,[x,2.2,-spec.grove.depth/2],'8Encoder Grove open-top rail');
 mesh(body,new THREE.BoxGeometry(3.4,.65,1.05),plastic,[0,1.2,-4.1],'8Encoder Grove latch bridge');
}
function build(host){
 addCadParts(host,data,{shell:materials.plastic(0x50544f,{roughness:.8})});board(host);connector(host);
 const mechanisms=CHANNELS.map(item=>channel(host,item));
 const leds=CHANNELS.map(item=>light(host,{number:item.number,y:item.y}));leds.push(light(host,{number:9,y:59}));
 const stableSwitch=slide(host);screw(host.body,[0,spec.mountY,-4.98],'back',1.4);
 host.add(new Component({id:'sensor',label:'8Encoder geometry anchor',meta:{role:'visual-anchor',scope:'no-counts-registers-firmware-or-bus'}}));
 host.encoderMechanisms=mechanisms;host.rgbLights=leds;host.stableSwitch=stableSwitch;
}
const keymap=Object.fromEntries(CHANNELS.map(c=>['Digit'+c.number,c.press]));
export class Model extends Device{
 static meta={id:'m5stack.unit.8encoder',name:spec.name,sku:spec.sku,vendor:'M5Stack',size:spec.size,keymap};
 build(){build(this);}
}
export class GroveModule extends Module{
 static meta={id:'m5stack.unit.8encoder.grove',name:spec.name,sku:spec.sku,connector:'grove'};
 build(options={}){buildGroveModuleAssembly(this,build,options);}
}
export {spec,CHANNELS};
export default Model;
