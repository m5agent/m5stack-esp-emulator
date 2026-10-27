import * as THREE from 'three';
import {Led,materials} from '../../core/index.js';
import {slab,mesh} from '../../modeling/parts.js';

// MAX30100 original datasheet pp8/27: package nominal 2.8 x 5.6 x 1.2;
// SENSOR +1.70 and LED -1.96 from its long-axis centre. M5's asymmetric
// front photograph fixes the LED end toward Grove. The installed Z seat,
// lens profile/material and rendered brightness remain visual inferences.
export const OPTICAL={
 centre:[-.0001859665,8.000472784],
 package:[2.8,5.6,1.2],seatZ:2.76,bodyDepth:.9,
 sensorOffset:1.70,emitterOffset:-1.96,
 sensorOuterDiameter:1.27,sensorInnerDiameter:.95,
 emitterFoot:[1.32,1.00],lensSeatZ:3.72,lensHeight:.24,
 centreFeature:[2.14,1.19],centreFeatureOffset:-.51,
};

class FixedRedLed extends Led{
 set(state){
  if(typeof state==='boolean')state={on:state};
  else if(typeof state==='string'||typeof state==='number')state={on:true};
  super.set({...state,color:0xff2820});
 }
}

function dome(radius,height){
 return new THREE.SphereGeometry(radius,48,20,0,Math.PI*2,0,Math.PI/2)
  .rotateX(Math.PI/2).scale(1,1,height/radius);
}

export function addOpticalAssembly(host){
 const o=OPTICAL,[cx,cy]=o.centre,group=new THREE.Group();
 group.name='Heart MAX30100 optical package';group.position.set(cx,cy,0);host.body.add(group);
 const body=slab(group,o.package[0],o.package[1],o.bodyDepth,.06,[0,0,o.seatZ],materials.plastic(0x131720,{roughness:.65,clearcoat:0,specularIntensity:.15}),[],.015);
 body.name='Heart MAX30100 nominal package body';
 // The p27 central rounded feature has a documented outline/offset; this
 // shallow relief and its finish are inferred from the unpowered photos.
 const centre=slab(group,...o.centreFeature,.03,.18,[0,o.centreFeatureOffset,o.seatZ+o.bodyDepth],materials.plastic(0x0b1018,{roughness:.45,clearcoat:0,specularIntensity:.15}),[],.006);
 centre.name='Heart MAX30100 central package feature';
 const outline=new THREE.Shape();outline.absarc(0,0,o.sensorOuterDiameter/2,0,Math.PI*2,false);
 const bore=new THREE.Path();bore.absarc(0,0,o.sensorInnerDiameter/2,0,Math.PI*2,true);outline.holes.push(bore);
 const rim=mesh(group,new THREE.ExtrudeGeometry(outline,{depth:.06,bevelEnabled:false,curveSegments:48}),materials.glossy(0x2e3440,{roughness:.26}),[0,o.sensorOffset,o.seatZ+o.bodyDepth],'Heart SENSOR circular aperture rim');
 const detector=mesh(group,dome(o.sensorInnerDiameter/2,o.lensHeight),materials.glossy(0x141a25,{roughness:.16}),[0,o.sensorOffset,o.lensSeatZ],'Heart SENSOR passive lens');
 const foot=slab(group,...o.emitterFoot,.06,.17,[0,o.emitterOffset,o.seatZ+o.bodyDepth],materials.plastic(0x211c26,{roughness:.55,clearcoat:.05,specularIntensity:.2}),[],.012);
 foot.name='Heart LED rounded rectangular aperture foot';
 const led=host.add(new FixedRedLed({id:'red-led',label:'MAX30100 visible red emitter',position:[cx,cy+o.emitterOffset,o.lensSeatZ],mesh:new THREE.Mesh(dome(.5,o.lensHeight),materials.glossy(0x281b22,{roughness:.17})),radius:.5,glowSize:1.35,color:0xff2820,meta:{role:'externally-driven-visual',colorMode:'fixed-red',emitter:'MAX30100 RED 660 nm',orientationEvidence:'Original MAX30100 pp8/27 asymmetric SENSOR/LED apertures matched to M5 U029 front photograph; LED end toward Grove',scope:'Default off; external visible brightness only. No measurement mode, heart-rate pulse, current mapping or human-visible IR.'}}));
 led.lens.name='Heart MAX30100 red-emitter lens';
 // A tiny recessed optical aperture must not use a camera-facing billboard:
 // at grazing views that plane can rise above the shell and paint its rim.
 // Keep the normal Led output API, with a depth-tested disk in the actual
 // aperture plane. The core shared gradient texture keeps its existing owner.
 const billboard=led.glow,glow=new THREE.Mesh(new THREE.CircleGeometry(.675,48),new THREE.MeshBasicMaterial({map:billboard.material.map,color:led.color,transparent:true,opacity:0,blending:THREE.AdditiveBlending,depthWrite:false,toneMapped:false}));
 billboard.removeFromParent();billboard.material.dispose();
 glow.name='Heart red aperture-aligned glow';glow.position.z=o.lensHeight+.002;glow.raycast=()=>{};glow.visible=false;led.object3d.add(glow);led.glow=glow;
 host.heartOpticalAssembly={group,body,centre,rim,detector,foot,led};
}
