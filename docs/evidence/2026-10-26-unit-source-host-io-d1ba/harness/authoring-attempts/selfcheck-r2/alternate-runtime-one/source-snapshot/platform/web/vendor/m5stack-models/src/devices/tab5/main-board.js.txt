import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {mesh} from '../../modeling/parts.js';

/** The actual edge notches leave space for recessed connector bodies, not cap planes. */
export function addMainBoard(parent){
 const w=77,h=74,r=1.3,left=-w/2,right=w/2,bottom=-h/2,top=h/2;
 const shape=new THREE.Shape();shape.moveTo(left+r,bottom);shape.lineTo(right-r,bottom);shape.absarc(right-r,bottom+r,r,-Math.PI/2,0,false);
 shape.lineTo(right,top-r);shape.absarc(right-r,top-r,r,0,Math.PI/2,false);shape.lineTo(left+r,top);shape.absarc(left+r,top-r,r,Math.PI/2,Math.PI,false);
 // [upper Y, lower Y, inside X] in board-local coordinates, sorted along its edge.
 for(const [hi,lo,x]of [[22,8,-32.9],[4.8,-4.8,-36.6],[-9.9,-16.1,-32.9],[-20.7,-31.3,-34.6]]){
  shape.lineTo(left,hi);shape.lineTo(x,hi);shape.lineTo(x,lo);shape.lineTo(left,lo);
 }
 shape.lineTo(left,bottom+r);shape.absarc(left+r,bottom+r,r,Math.PI,Math.PI*1.5,false);shape.closePath();
 for(let c=0;c<2;c++)for(let row=0;row<15;row++)shape.holes.push(roundedRect(1.85,1.85,.12,{cx:9.3+(c-.5)*2.54+22.5,cy:(row-7)*2.54,path:new THREE.Path(),clockwise:true}));
 return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth:1,bevelEnabled:false,curveSegments:12}),materials.plastic(0x2e493d,{roughness:.9}),[-22.5,0,-4.8],'Main PCB with connector clearances');
}
