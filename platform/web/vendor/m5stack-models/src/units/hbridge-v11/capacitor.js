import *as THREE from'three';import{materials}from'../../core/index.js';import{mesh}from'../../modeling/parts.js';import{spec}from'./dimensions.js';
/** Supplied470µF capacitor seated in the same plug's HV/G slots, per own install photo. */
export function addCapacitor(host,parent){
 const group=new THREE.Group();group.name='HBridge v1.1 supplied470µF capacitor and two inserted leads';parent.add(group);
 const metal=materials.metal(0xafb4b0,{roughness:.36}),sleeve=materials.plastic(0x18202a,{roughness:.46}),rubber=materials.plastic(0x252925,{roughness:.84}),centerX=-3.96,centerY=30.2,z=.35,r=spec.capacitor.radiusMm,length=spec.capacitor.lengthMm;
 const can=mesh(group,new THREE.CylinderGeometry(r,r,length,64),sleeve,[centerX,centerY,z],'HBridge v1.1 actual cylindrical470µF black sleeve');mesh(group,new THREE.CylinderGeometry(r-.2,r-.2,.18,64),metal,[centerX,centerY+length/2+.04,z],'HBridge v1.1 recessed aluminium capacitor vent end');mesh(group,new THREE.CylinderGeometry(r-.2,r-.2,.3,64),rubber,[centerX,centerY-length/2+.05,z],'HBridge v1.1 rubber lead seal');
 // Physical narrow sleeve stripe and pressure-relief score, no text/voltage rating invented.
 const stripe=mesh(group,new THREE.CylinderGeometry(r+.012,r+.012,length-.65,24,1,true,1.13,.42),materials.plastic(0x9da9b6,{roughness:.63}),[centerX,centerY,z],'HBridge v1.1 capacitor sleeve polarity stripe appearance');
 for(const angle of[0,Math.PI/2]){const vent=mesh(group,new THREE.BoxGeometry(4.3,.025,.08),materials.plastic(0x65706b),[centerX,centerY+length/2+.14,z],'HBridge v1.1 pressure-relief metal score');vent.rotation.y=angle;}
 const leads=[];for(const x of spec.terminal.pinX.slice(0,2)){const pts=[new THREE.Vector3(x,7.5,.35),new THREE.Vector3(x,13,.35),new THREE.Vector3(x,19,.35),new THREE.Vector3(x,centerY-length/2+.4,.35)];leads.push(mesh(group,new THREE.TubeGeometry(new THREE.CatmullRomCurve3(pts),32,.26,8,false),metal,[0,0,0],'HBridge v1.1 capacitor real inserted HV/G tinned lead'));}
 group.userData={role:'physical-accessory',capacitanceLabel:'470µF',dimensionsInferred:true,scope:'Appearance only. Both leads occupy the existing plug wire entries; no extra port, polarity enforcement, charging, discharging, current or protection behavior'};return{group,can,stripe,leads};
}
