import * as THREE from 'three';
import {Button,Led,materials} from '../../core/index.js';
import {VisualJoint} from '../../core/components/VisualJoint.js';
import {roundedRect} from '../../core/geometry.js';
import {mesh,slab} from '../../modeling/parts.js';
import {refineOpenTopGrove} from '../shared/open-top-grove.js';

// Collar centre is fitted to the unchanged official z=6 ring. Ø10 is from
// U135's own drawing. Concealed package/board/press dimensions remain inferred.
export const ENCODER_ASSEMBLY=Object.freeze({axis:Object.freeze([-.0130000268,7.9499998353,6]),capRadius:5,capBottom:6.45,capTop:19.38,pcbZ:-3.9,pcbThickness:.8,ledPositions:Object.freeze([Object.freeze([-6.8,-10.4,-3.1]),Object.freeze([6.8,-10.4,-3.1])])});

function replaceBoard(host){
 const old=host.body.getObjectByName('Unit PCB');
 if(!old?.isMesh)throw new Error('Encoder requires its original board before reconstruction');
 const shape=new THREE.Shape();shape.moveTo(-1.5,16);shape.lineTo(1.5,16);shape.lineTo(1.5,13.8);shape.lineTo(7.7,13.8);shape.lineTo(8.2,13.3);shape.lineTo(8.2,12.4);shape.lineTo(9.4,11.7);shape.lineTo(9.4,.4);shape.lineTo(8,.4);
 shape.absarc(8,-4,4.4,Math.PI/2,Math.PI*1.5,false);shape.lineTo(9.4,-8.4);shape.lineTo(9.4,-11.7);shape.lineTo(8.2,-12.4);shape.lineTo(8.2,-13.3);shape.lineTo(7.7,-13.8);shape.lineTo(5.1,-13.8);shape.lineTo(5.1,-8.85);shape.lineTo(-5.1,-8.85);shape.lineTo(-5.1,-13.8);shape.lineTo(-7.7,-13.8);shape.lineTo(-8.2,-13.3);shape.lineTo(-8.2,-12.4);shape.lineTo(-9.4,-11.7);shape.lineTo(-9.4,-8.4);shape.lineTo(-8,-8.4);
 shape.absarc(-8,-4,4.4,Math.PI*1.5,Math.PI*2.5,false);shape.lineTo(-9.4,.4);shape.lineTo(-9.4,11.7);shape.lineTo(-8.2,12.4);shape.lineTo(-8.2,13.3);shape.lineTo(-7.7,13.8);shape.lineTo(-1.5,13.8);shape.closePath();
 // Pair the clockwise PCB outline with counterclockwise inner walls.
 shape.holes.push(roundedRect(5.8,5.8,2.9,{cx:0,cy:-4,path:new THREE.Path(),clockwise:false}));
 for(const cx of [-3,-1,1,3])shape.holes.push(roundedRect(.6,.6,.3,{cx,cy:-8.4,path:new THREE.Path(),clockwise:false}));
 const material=old.material;old.removeFromParent();old.geometry.dispose();
 const board=mesh(host.body,new THREE.ExtrudeGeometry(shape,{depth:.8,bevelEnabled:false,curveSegments:32}),material,[0,0,-3.9],'Encoder PCB with open boss and Grove relief');
 host.encoderBoard=board;return board;
}

function knob(parent){
 const group=new THREE.Group();group.name='Encoder moving knob';parent.add(group);
 const black=materials.plastic(0x171c1e,{roughness:.82}),bottom=6.45,top=19.18;
 const profile=[[2.35,bottom],[4.78,bottom],[4.65,top],[0,top],[0,10],[2.35,10],[2.35,bottom]].map(p=>new THREE.Vector2(...p));
 mesh(group,new THREE.LatheGeometry(profile,96).rotateX(Math.PI/2),black,[0,0,0],'Encoder black cap with blind shaft bore');
 // Solid annular sectors keep every ridge at or inside the documented Ø10.
 const sector=new THREE.Shape();const a=.038;sector.moveTo(4.6*Math.cos(-a),4.6*Math.sin(-a));sector.lineTo(5*Math.cos(-a),5*Math.sin(-a));sector.absarc(0,0,5,-a,a,false);sector.lineTo(4.6*Math.cos(a),4.6*Math.sin(a));sector.absarc(0,0,4.6,a,-a,true);sector.closePath();
 const ribGeometry=new THREE.ExtrudeGeometry(sector,{depth:11.6,bevelEnabled:false,curveSegments:4});
 for(let i=0;i<24;i++){const rib=mesh(group,i?ribGeometry.clone():ribGeometry,black.clone(),[0,0,6.95],'Encoder solid grip ridge '+i);rib.rotation.z=i*Math.PI/12;}
 const radius=4.1,half=.4,y=Math.sqrt(radius*radius-half*half),angle=Math.atan2(y,half),insert=new THREE.Shape();
 insert.moveTo(-half,y);insert.lineTo(-half,radius-1);insert.lineTo(half,radius-1);insert.lineTo(half,y);insert.absarc(0,0,radius,angle,Math.PI-angle,true);insert.closePath();
 mesh(group,new THREE.ExtrudeGeometry(insert,{depth:.28,bevelEnabled:false,curveSegments:48}),materials.plastic(0xdbddd8,{roughness:.62}),[0,0,19.1],'Encoder solid white insert with edge notch');
 return group;
}

function shellDiffusion(host){
 const front=host.parts.front,material=front.material.clone();front.material=material;
 // Both native parts originally share the old shell material; rear still owns
 // that original, so only the new independent front material is added here.
 const colors=[new THREE.Color(0),new THREE.Color(0)],brightness=[{value:0},{value:0}];
 const uniforms={encoderColor0:{value:colors[0]},encoderColor1:{value:colors[1]},encoderBrightness0:brightness[0],encoderBrightness1:brightness[1]};
 material.onBeforeCompile=shader=>{
  Object.assign(shader.uniforms,uniforms);
  shader.vertexShader=shader.vertexShader.replace('#include <common>','#include <common>\nvarying vec3 vEncoderPosition;').replace('#include <begin_vertex>','#include <begin_vertex>\nvEncoderPosition = position;');
  shader.fragmentShader=shader.fragmentShader.replace('#include <common>','#include <common>\nvarying vec3 vEncoderPosition;\nuniform vec3 encoderColor0;\nuniform vec3 encoderColor1;\nuniform float encoderBrightness0;\nuniform float encoderBrightness1;');
  shader.fragmentShader=shader.fragmentShader.replace('#include <emissivemap_fragment>',`#include <emissivemap_fragment>
    vec2 encoderQ0 = (vEncoderPosition.xy - vec2(-6.8, -10.4)) / vec2(3.3, 3.4);
    vec2 encoderQ1 = (vEncoderPosition.xy - vec2(6.8, -10.4)) / vec2(3.3, 3.4);
    float encoderLower = 1.0 - smoothstep(-6.4, -5.6, vEncoderPosition.y);
    totalEmissiveRadiance += encoderLower * 1.5 * (encoderColor0 * encoderBrightness0 * exp(-2.0 * dot(encoderQ0, encoderQ0)) + encoderColor1 * encoderBrightness1 * exp(-2.0 * dot(encoderQ1, encoderQ1)));`);
 };
 material.customProgramCacheKey=()=> 'encoder-native-shell-diffusion-v1';
 host.encoderShellDiffusion={material,uniforms,scope:'Local emissive appearance on the unchanged native front shell, based on the official lit demo; not an optical/material simulation.'};
 return (index,color,value)=>{colors[index].copy(color);brightness[index].value=value;};
}

class EncoderLed extends Led{
 set(state){super.set(state);this.onDiffusion?.(this.color,this.brightness);}
 dispose(){this.onDiffusion=null;super.dispose();}
}

export function addEncoderAssembly(host){
 replaceBoard(host);refineOpenTopGrove(host,'encoder');
 // The four inferred folded solder tails bridge the rear web to real board
 // drillings. They do not turn the visual connector into an electrical model.
 for(const [i,cx]of [-3,-1,1,3].entries()){
  const metal=materials.metal(0xb4ad91,{roughness:.42});
  mesh(host.body,new THREE.BoxGeometry(.32,1.2,.32),metal,[cx,-9,-.75],'Encoder Grove folded tail '+i);
  mesh(host.body,new THREE.BoxGeometry(.32,.32,3.3),metal.clone(),[cx,-8.4,-2.4],'Encoder Grove board leg '+i);
  const pad=new THREE.Shape();pad.absarc(0,0,.48,0,Math.PI*2,false);const bore=new THREE.Path();bore.absarc(0,0,.2,0,Math.PI*2,true);pad.holes.push(bore);
  mesh(host.body,new THREE.ExtrudeGeometry(pad,{depth:.08,bevelEnabled:false,curveSegments:16}),metal.clone(),[cx,-8.4,-3.12],'Encoder Grove solder fillet '+i);
 }
 const [x,y]=ENCODER_ASSEMBLY.axis;
 slab(host.body,11.2,11.0,2.4,.45,[x,y,-3.1],materials.metal(0x969d92,{roughness:.58}),[],.06).name='Encoder fixed stamped body';
 slab(host.body,10.7,10.5,.25,.45,[x,y,-.7],materials.metal(0xb7bca9,{roughness:.48}),[],.03).name='Encoder fixed retaining plate';
 for(const sign of [-1,1])for(const dy of [-3.4,0,3.4])slab(host.body,1.35,.65,.35,.1,[x+sign*5.85,y+dy,-2.0],materials.metal(0xa6ad9b,{roughness:.45}),[],.02).name='Encoder solder tab';
 const cap=knob(host.body);
 mesh(cap,new THREE.CylinderGeometry(2.25,2.25,10.3,48).rotateX(Math.PI/2),materials.metal(0x8c9189,{roughness:.5}),[0,0,4.35],'Encoder moving shaft');
 const press=host.add(new Button({id:'press',label:'Encoder press',mesh:cap,position:[x,y,0],travel:.35,meta:{role:'visual-control',travelSource:'Photo-derived visual travel; no switch or pulse emulation'}}));
 const rotation=host.add(new VisualJoint({id:'rotation',label:'Encoder knob rotation',position:[x,y,6],axis:[0,0,1],continuous:true,meta:{axisEvidence:'Official U135 native collar circle fit; cap Ø10 from own drawing',demoRpmMax:60}}));rotation.adopt(press.object3d);
 const diffuse=shellDiffusion(host),leds=[];
 for(const [i,position]of ENCODER_ASSEMBLY.ledPositions.entries()){
  const [lx,ly,lz]=position;
  slab(host.body,3.2,3.2,1.25,.18,[lx,ly,lz],materials.plastic(0xd8deca,{roughness:.68}),[],.04).name='Encoder internal SK6812 package '+i;
  const lens=new THREE.Mesh(new THREE.CylinderGeometry(1.05,1.05,.12,32).rotateX(Math.PI/2),materials.glossy(0xbec6b1,{roughness:.32}));
  const led=host.add(new EncoderLed({id:'led'+i,label:'Encoder lower RGB '+i,position:[lx,ly,lz+1.31],mesh:lens,radius:1.05,glowSize:2,lensColor:0xbec6b1,meta:{role:'externally-driven-visual',physicalPlacement:'Inside the lower white shell beside Grove; official PCB photo and lit video',mapping:'left/right are visual addresses, schematic LED1/LED2 order unconfirmed'}}));
  led.glow.visible=false;led.onDiffusion=(color,value)=>diffuse(i,color,value);leds.push(led);
 }
 host.encoderAssembly={press,rotation,cap,leds,dimensions:ENCODER_ASSEMBLY};
}
