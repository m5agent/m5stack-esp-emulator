import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {addCadParts} from '../../modeling/cad.js';
import {mesh,slab,FACE} from '../../modeling/parts.js';
import motionData from './geometry-data-motion.js';
import {servoPackage} from './servo-packages.js';

/** Exposed mechanical bodies behind the real moving head/neck openings. */
export function addMotionMechanics(host){
 const parts=addCadParts({body:host.body},motionData,{arm:materials.plastic(0x9ca7a0,{roughness:.78})});
 Object.assign(host.parts,parts);
 const group=new THREE.Group();group.name='Neck servo packages';host.body.add(group);
 const plastic=materials.plastic(0x202b25,{roughness:.87}),metal=materials.metal(0x89958a,{roughness:.47});
 // Package outlines are constrained by the official cover interiors and photos,
 // not claimed as a SCS0009 manufacturing model or a motor/servo simulation.
 const pitchServo=servoPackage(group,{name:'Pitch servo body',position:[-18,6.65,-2],basis:[[0,0,-1],[0,-1,0],[-1,0,0]]});
 const yawServo=servoPackage(group,{name:'Yaw servo body',position:[0,-26.2,-2],basis:[[0,0,-1],[1,0,0],[0,-1,0]]});
 slab(group,30,20,5.6,1.2,[0,-13,-27.6],materials.plastic(0x167da3,{roughness:.64}),[],.08).name='550 mAh battery visual envelope';
 for(const [x,length,r,name]of [[21.7,5,1.8,'Pitch passive bearing pin']]){
  mesh(group,new THREE.CylinderGeometry(r,r,length,40).rotateZ(Math.PI/2),metal,[x,6.65,-2],name);
 }
 mesh(group,new THREE.CylinderGeometry(3.5,3.5,2.2,40),metal,[0,-24.05,-2],'Yaw shaft thrust collar');
 const bearing=new THREE.Shape();bearing.absarc(0,0,5.5,0,Math.PI*2,false);const bore=new THREE.Path();bore.absarc(0,0,1.8,0,Math.PI*2,true);bearing.holes.push(bore);
 const race=mesh(host.body,new THREE.ExtrudeGeometry(bearing,{depth:3,bevelEnabled:false,curveSegments:48}),metal,[20.9,6.65,-2],'Pitch passive bearing race');race.quaternion.copy(FACE.right);
 const bolt=mesh(host.body,new THREE.CylinderGeometry(.75,.75,4.4,32).rotateZ(Math.PI/2),metal,[-23,6.65,-2],'Pitch arm axle fastener');
 group.userData={role:'visual-mechanical-packages',dimensionSource:'Photo-derived solids inside the official neck/cover envelope; no electrical or firmware behavior'};
 host.body.updateMatrixWorld(true);host.body.attach(yawServo.output);
 return {fixedParts:[yawServo.output],headParts:[parts['pitch-servo-arm'],parts['pitch-bearing-fixture'],race,bolt,pitchServo.output],neck:group,pitchServo,yawServo};
}
