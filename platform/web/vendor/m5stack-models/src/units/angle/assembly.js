import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {VisualJoint} from '../../core/components/VisualJoint.js';
import {mesh,slab} from '../../modeling/parts.js';
import {roundedRect} from '../../core/geometry.js';
import {refineOpenTopGrove} from '../shared/open-top-grove.js';

// U005's own drawing specifies Ø9.5, Y=8, shell depth8 and overall22.3.
// The rectangular opening is a separate native-shell datum, not the shaft axis.
export const ANGLE_ASSEMBLY=Object.freeze({axis:Object.freeze([0,8,4]),openingCentre:Object.freeze([-.0001706543,7.5004802246]),capRadius:4.75,capBottom:5.5,capTop:18.3});

function movingCap(parent){
 const group=new THREE.Group();group.name='Angle moving knob';group.position.set(0,8,0);parent.add(group);
 const black=materials.plastic(0x24292a,{roughness:.78}),bottom=5.5,top=18.1;
 // Closed solid with a genuine blind shaft bore. The rib envelope stays Ø9.5.
 const profile=[[2.05,bottom],[4.65,bottom],[4.65,6.8],[4.38,top],[0,top],[0,9],[2.05,9],[2.05,bottom]].map(p=>new THREE.Vector2(...p));
 mesh(group,new THREE.LatheGeometry(profile,96).rotateX(Math.PI/2),black,[0,0,0],'Angle cap with blind shaft bore');
 const sector=new THREE.Shape(),a=.038;sector.moveTo(4.36*Math.cos(-a),4.36*Math.sin(-a));sector.lineTo(4.75*Math.cos(-a),4.75*Math.sin(-a));sector.absarc(0,0,4.75,-a,a,false);sector.lineTo(4.36*Math.cos(a),4.36*Math.sin(a));sector.absarc(0,0,4.36,a,-a,true);sector.closePath();
 const geometry=new THREE.ExtrudeGeometry(sector,{depth:10.75,bevelEnabled:false,curveSegments:4});
 for(let i=0;i<24;i++){const rib=mesh(group,i?geometry.clone():geometry,black.clone(),[0,0,6.85],'Angle solid grip ridge '+i);rib.rotation.z=i*Math.PI/12;}
 // Blue insert with a short open edge notch; no painted stripe to its centre.
 const r=3.92,half=.32,y=Math.sqrt(r*r-half*half),angle=Math.atan2(y,half),shape=new THREE.Shape();
 shape.moveTo(-half,y);shape.lineTo(-half,r-.95);shape.lineTo(half,r-.95);shape.lineTo(half,y);shape.absarc(0,0,r,angle,Math.PI-angle,true);shape.closePath();
 mesh(group,new THREE.ExtrudeGeometry(shape,{depth:.25,bevelEnabled:false,curveSegments:48}),materials.plastic(0x008ec0,{roughness:.58}),[0,0,18.05],'Angle solid blue insert with edge notch');
 mesh(group,new THREE.CylinderGeometry(1.95,1.95,7.9,48).rotateX(Math.PI/2),materials.metal(0x969b91,{roughness:.5}),[0,0,4.95],'Angle moving shaft');
 return group;
}

function replaceBoard(host){
 const old=host.body.getObjectByName('Unit PCB');
 if(!old?.isMesh)throw new Error('Angle requires its original board before reconstruction');
 // Conservative inferred outline inside U005's own CAD cavity. Side boss
 // reliefs are open edge contours; the central screw boss has a real bore.
 const shape=new THREE.Shape();shape.moveTo(-5.4,13.4);shape.lineTo(5.4,13.4);shape.lineTo(9.4,9.4);shape.lineTo(9.4,.2);shape.lineTo(8,.2);
 shape.absarc(8,-4,4.2,Math.PI/2,Math.PI*1.5,false);shape.lineTo(9.4,-8.2);shape.lineTo(9.4,-9.4);shape.lineTo(5.4,-13.4);shape.lineTo(5.1,-13.4);shape.lineTo(5.1,-8.85);shape.lineTo(-5.1,-8.85);shape.lineTo(-5.1,-13.4);shape.lineTo(-5.4,-13.4);shape.lineTo(-9.4,-9.4);shape.lineTo(-9.4,-8.2);shape.lineTo(-8,-8.2);
 shape.absarc(-8,-4,4.2,Math.PI*1.5,Math.PI*2.5,false);shape.lineTo(-9.4,.2);shape.lineTo(-9.4,9.4);shape.lineTo(-5.4,13.4);shape.closePath();
 // Pair the clockwise PCB outline with counterclockwise inner walls.
 shape.holes.push(roundedRect(4.4,4.4,2.2,{cx:0,cy:-4,path:new THREE.Path(),clockwise:false}));
 for(const cx of [-3,-1,1,3])shape.holes.push(roundedRect(.6,.6,.3,{cx,cy:-8.4,path:new THREE.Path(),clockwise:false}));
 const material=old.material;old.removeFromParent();old.geometry.dispose();
 const board=mesh(host.body,new THREE.ExtrudeGeometry(shape,{depth:.8,bevelEnabled:false,curveSegments:32}),material,[0,0,.2],'Angle PCB with open boss and Grove relief');host.angleBoard=board;return board;
}

export function addAngleAssembly(host){
 replaceBoard(host);
 refineOpenTopGrove(host,'angle');
 for(const [i,cx]of [-3,-1,1,3].entries()){
  const metal=materials.metal(0xb4ad91,{roughness:.42});
  mesh(host.body,new THREE.BoxGeometry(.32,1.4,.32),metal,[cx,-9,1.25],'Angle Grove folded tail '+i);
  mesh(host.body,new THREE.BoxGeometry(.32,.32,1.25),metal.clone(),[cx,-8.4,.775],'Angle Grove board leg '+i);
  const pad=new THREE.Shape();pad.absarc(0,0,.48,0,Math.PI*2,false);const bore=new THREE.Path();bore.absarc(0,0,.2,0,Math.PI*2,true);pad.holes.push(bore);
  mesh(host.body,new THREE.ExtrudeGeometry(pad,{depth:.08,bevelEnabled:false,curveSegments:16}),metal.clone(),[cx,-8.4,1.0],'Angle Grove solder fillet '+i);
 }
 const [x,y]=ANGLE_ASSEMBLY.openingCentre,shaftHole=(radius)=>({w:radius*2,h:radius*2,r:radius,cx:-x,cy:8-y});
 const body=slab(host.body,9.7,11.7,1.9,.08,[x,y,1],materials.plastic(0x1677b6,{roughness:.7}),[shaftHole(2.1)],0);body.name='Angle fixed potentiometer body';
 const base=slab(host.body,9.98,11.98,1.05,0,[x,y,2.9],materials.plastic(0x168bcc,{roughness:.68}),[shaftHole(2.1)],0);base.name='Angle fixed blue base';
 const holes=[shaftHole(2.1),...[-3.45,3.45].map(cx=>({w:.85,h:.85,r:.425,cx,cy:-4.35}))];
 const frame=slab(host.body,9.7,11.5,.4,.1,[x,y,3.95],materials.metal(0xaab2b1,{roughness:.48}),holes,0);frame.name='Angle fixed stamped retaining frame';
 const cap=movingCap(host.body);
 const rotation=host.add(new VisualJoint({id:'rotation',label:'Angle knob position',position:[0,8,4],axis:[0,0,1],meta:{axisEvidence:'Official U005 drawing: 8 mm from housing top; Ø9.5 cap; own native aperture is independently centred at Y7.50048',visualRangeDeg:[-150,150],rangeEvidence:'Viewer range only; official mechanical travel and zero offset are unconfirmed'}}));rotation.adopt(cap);
 host.angleAssembly={rotation,cap,body,base,frame,dimensions:ANGLE_ASSEMBLY};
}
