import * as THREE from 'three';
import {roundedRect} from '../../core/geometry.js';
/** Product-local analytic outlines; no native CAD or sibling product geometry. */
export function shapeRect(w,h,r=0,cx=0,cy=0){return roundedRect(w,h,Math.max(.0001,r),{cx,cy});}
export function hole(shape,w,h,r,cx=0,cy=0){shape.holes.push(roundedRect(w,h,Math.max(.0001,r),{cx,cy,path:new THREE.Path(),clockwise:true}));return shape;}
export function circleHole(shape,x,y,r){const h=new THREE.Path();h.absarc(x,y,r,0,-Math.PI*2,true);shape.holes.push(h);return shape;}
export function extrude(shape,depth){return new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:32});}
export function polygon(points){const s=new THREE.Shape();points.forEach(([x,y],i)=>i?s.lineTo(x,y):s.moveTo(x,y));s.closePath();return s;}
export function mainFront(){const s=new THREE.Shape();s.moveTo(-12,-12);s.lineTo(2,-12);s.lineTo(2,18.25);s.lineTo(10,18.25);s.lineTo(10,-12);s.lineTo(12,-12);s.lineTo(12,25);s.absarc(9,25,3,0,Math.PI/2,false);s.lineTo(-9,28);s.absarc(-9,25,3,Math.PI/2,Math.PI,false);s.closePath();return s;}
export function lowerFront(){const s=new THREE.Shape();s.moveTo(-12,-12);s.lineTo(-12,-25);s.absarc(-9,-25,3,Math.PI,Math.PI*1.5,false);s.lineTo(9,-28);s.absarc(9,-25,3,-Math.PI/2,0,false);s.lineTo(12,-12);s.closePath();for(const x of[-8,8])circleHole(s,x,-16,2.425);return s;}
export function ring(outer,inner){const s=new THREE.Shape();s.absarc(0,0,outer,0,Math.PI*2,false);return circleHole(s,0,0,inner);}
export function endCorner(signX,signY){const s=new THREE.Shape(); // exact quadrant strip, mirrored below
 s.moveTo(5.25,26.9);s.lineTo(9,26.9);s.absarc(9,25,1.9,Math.PI/2,0,true);s.lineTo(10.9,24.9);s.lineTo(12,24.9);s.lineTo(12,25);s.absarc(9,25,3,0,Math.PI/2,false);s.lineTo(5.25,28);s.closePath();
 const g=extrude(s,signY>0?9.21:7.46);g.translate(0,0,-4.61);if(signX<0)g.scale(-1,1,1);if(signY<0)g.scale(1,-1,1);if(signX*signY<0){const idx=g.index;if(idx){for(let i=0;i<idx.count;i+=3){const t=idx.getX(i+1);idx.setX(i+1,idx.getX(i+2));idx.setX(i+2,t);}}else{for(const attr of Object.values(g.attributes))for(let i=0;i<attr.count;i+=3)for(let k=0;k<attr.itemSize;k++){const t=attr.array[(i+1)*attr.itemSize+k];attr.array[(i+1)*attr.itemSize+k]=attr.array[(i+2)*attr.itemSize+k];attr.array[(i+2)*attr.itemSize+k]=t;}}}g.computeVertexNormals();return g;
}
export function headerCarrier(){const points=[[-3.75,-2.46],[-2.85,-2.46],[-2.54,-1.8],[-2.23,-2.46],[-.31,-2.46],[0,-1.8],[.31,-2.46],[2.23,-2.46],[2.54,-1.8],[2.85,-2.46],[3.75,-2.46],[3.75,2.46],[2.85,2.46],[2.54,1.8],[2.23,2.46],[.31,2.46],[0,1.8],[-.31,2.46],[-2.23,2.46],[-2.54,1.8],[-2.85,2.46],[-3.75,2.46]];const s=polygon(points);for(const x of[-2.54,0,2.54])for(const y of[-1.27,1.27])hole(s,.66,.66,.015,x,y);return s;}
