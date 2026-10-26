import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {mesh,slab,FACE} from '../../modeling/parts.js';

// SCS0009 outline: official linked FEETECH specification, page 6/8.
// 23.3 x 11 mm main case, 12.1 mm mounting-ear width, 25.25 mm
// face-to-back depth, 3.2 mm shaft. Placement in K151 remains photo derived.
export function servoPackage(parent,{name,position,basis}){
 const group=new THREE.Group();group.name=name;group.position.fromArray(position);group.quaternion.setFromRotationMatrix(new THREE.Matrix4().makeBasis(...basis.map(a=>new THREE.Vector3(...a))));parent.add(group);
 const black=materials.plastic(0x202823,{roughness:.79}),seam=materials.plastic(0x111913,{roughness:.88}),metal=materials.metal(0xa8a78b,{roughness:.4});
 slab(group,23.3,11,16.8,.5,[5.8,0,-25.25],black,[],.06).name=`${name} motor case`;
 slab(group,23.3,11,.17,.5,[5.8,0,-8.48],seam,[],.02).name=`${name} case seam`;
 slab(group,23.3,11,4.65,.5,[5.8,0,-8.45],black,[],.06).name=`${name} gearbox shoulder`;
 // PDF p6 shows a large output-gear end tapering to a smaller idler end,
 // not two equal semicircles. The 5.7 mm centre spacing is annotated;
 // the small radius (~2.8 mm) is traced from that drawing, not dimensioned.
 // Cap depth/hidden steps remain appearance approximations.
 const largeRadius=5.5,smallRadius=2.8,centres=5.7,tangent=Math.acos((largeRadius-smallRadius)/centres),cap=new THREE.Shape();
 cap.absarc(0,0,largeRadius,tangent,Math.PI*2-tangent,false);
 cap.lineTo(centres+smallRadius*Math.cos(tangent),-smallRadius*Math.sin(tangent));
 cap.absarc(centres,0,smallRadius,Math.PI*2-tangent,Math.PI*2+tangent,false);cap.closePath();
 mesh(group,new THREE.ExtrudeGeometry(cap,{depth:3.8,bevelEnabled:false,curveSegments:36}),black,[0,0,-3.8],`${name} rounded gearbox cap`);
 // The 32.5 x 12.1 measurement is the two-ear envelope, not a full-width
 // rectangular plate across the 23.3 x 11 case. PDF p6 puts the ear holes at
 // -8.55 and 5.7+14.25 relative to the output centre. The body-centre offset
 // 5.8 remains drawing-derived rather than an annotated dimension.
 for(const [side,min,max,hole]of [['front',-10.55,-5.85,-8.55],['rear',17.45,21.95,19.95]]){
  const center=(min+max)/2;
  const ear=slab(group,max-min,12.1,1.6,.6,[center,0,-8.45],black,[{w:2,h:2,r:1,cx:hole-center}],.03);ear.name=`${name} ${side} mounting ear`;
  ear.userData={role:'servo-mounting-ear',envelopeMm:[32.5,12.1],holeXmm:hole,source:'SCS0009.pdf p6; end tabs, not a rectangular plate across the case'};
 }
 const output=new THREE.Group();output.name=`${name} rotary output`;output.userData.role='rotary-output';group.add(output);
 // 20T (OD3.95 mm) and the 3.2 mm length are annotated in PDF p6.
 // OD is the tooth-tip envelope, not a root cylinder to add teeth outside.
 // The 1.75 mm root radius and straight flanks are visual approximations;
 // the drawing does not dimension a manufacturing spline tooth profile.
 const shaftRadius=1.975,rootRadius=1.75,pitch=Math.PI*2/20,spline=new THREE.Shape();spline.moveTo(rootRadius,0);
 for(let i=0;i<20;i++){
  const start=(i+.3)*pitch,end=(i+.7)*pitch;
  spline.lineTo(shaftRadius*Math.cos(start),shaftRadius*Math.sin(start));spline.absarc(0,0,shaftRadius,start,end,false);
  spline.lineTo(rootRadius*Math.cos((i+1)*pitch),rootRadius*Math.sin((i+1)*pitch));
 }
 spline.closePath();mesh(output,new THREE.ExtrudeGeometry(spline,{depth:3.2,bevelEnabled:false,curveSegments:4}),metal,[0,0,0],`${name} splined output`);
 output.userData.spline={teeth:20,outerDiameterMm:3.95,lengthMm:3.2,rootRadiusMm:rootRadius,toothProfileEvidence:'20T, OD3.95 and length3.2 from SCS0009.pdf p6; root radius and straight flanks are appearance approximations, not manufacturing data'};
 for(const x of [-4.2,15.8])for(const y of [-4.1,4.1])mesh(group,new THREE.CylinderGeometry(.55,.55,.2,20).rotateX(Math.PI/2),materials.metal(0xa0aaa0,{roughness:.6}),[x,y,-25.3],`${name} back case screw`);
 const socket=new THREE.Group();socket.name=`${name} cable socket`;socket.position.set(5.8,0,-25.3);socket.quaternion.copy(FACE.back);group.add(socket);
 const white=materials.plastic(0xc4ccc0,{roughness:.7});
 slab(socket,7.8,3.2,1.1,.2,[0,0,0],white,[{w:6.8,h:2.2,r:.1}],.03).name=`${name} cable socket shroud`;
 const contacts=[];for(let i=0;i<3;i++)contacts.push(mesh(socket,new THREE.BoxGeometry(.4,.4,.65),metal,[(i-1)*2.54,0,.68],`${name} cable contact ${i+1}`));
 group.userData={role:'visual-servo-package',model:'SCS0009',caseMm:[23.3,11,25.25],earWidthMm:12.1,shaftLengthMm:3.2,capOutline:{centreSpacingMm:centres,radiiMm:[largeRadius,smallRadius],smallRadiusEvidence:'Approximate trace of the unequal-radius top-view outline in SCS0009.pdf p6, not an annotated radius'},source:'Official linked SCS0009.pdf p6; K151 placement inferred; no servo behavior'};
 return {group,contacts,socket,output};
}
