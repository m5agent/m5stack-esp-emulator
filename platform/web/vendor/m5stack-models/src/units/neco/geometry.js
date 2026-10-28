import * as THREE from 'three';
import{mesh}from'../../modeling/parts.js';
import{materials}from'../../core/index.js';
import{roundedRect}from'../../core/geometry.js';
import{mountingCenters}from'./dimensions.js';
export{THREE,materials,roundedRect};
export const TAU=Math.PI*2;
export function hole(shape,x,y,r){const p=new THREE.Path();p.absarc(x,y,r,0,TAU,false);shape.holes.push(p);}
export function solid(parent,shape,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(shape,{depth,bevelEnabled:false,curveSegments:36}),material,position,name);}
export function ring(parent,outer,inner,depth,position,material,name){const s=new THREE.Shape();s.absarc(0,0,outer,0,TAU,false);hole(s,0,0,inner);return solid(parent,s,depth,position,material,name);}
export function box(parent,size,position,material,name){return mesh(parent,new THREE.BoxGeometry(...size),material,position,name);}
export function boardShape(){
 const s=new THREE.Shape();s.moveTo(0,22.3);
 s.bezierCurveTo(1.6,22.3,2.6,21.9,3.8,20.6);
 // Cubic fitted to the centre of the exact drawing's outer stroke (max sampled
 // deviation 0.033mm); this keeps the real perimeter under every RGB footprint.
 s.bezierCurveTo(15.065277493681688,7.166666666666667,20.61842249787154,-6.266666666666667,23.48,-19.7);
 s.bezierCurveTo(23.55,-19.9,23.55,-20,23.55,-20.25);
 s.bezierCurveTo(23.55,-21.38,22.63,-22.3,21.5,-22.3);
 s.quadraticCurveTo(0,-17.9,-21.5,-22.3);
 s.bezierCurveTo(-22.63,-22.3,-23.55,-21.38,-23.55,-20.25);
 s.bezierCurveTo(-23.55,-20,-23.55,-19.9,-23.48,-19.7);
 s.bezierCurveTo(-20.61842249787154,-6.266666666666667,-15.065277493681688,7.166666666666667,-3.8,20.6);
 s.bezierCurveTo(-2.6,21.9,-1.6,22.3,0,22.3);s.closePath();
 for(const[i,[x,y]]of mountingCenters.entries())hole(s,x,y,i<2?1.1:1.28);
 return s;
}
// Two actual upright sockets have their contact rows along PCB Y. Their solder
// tails face outward in opposite X directions, as in U163's own rear photograph.
export function socketQuaternion(id){
 const x=new THREE.Vector3(0,id==='grove'?-1:1,0),y=new THREE.Vector3(0,0,-1),z=x.clone().cross(y);
 return new THREE.Quaternion().setFromRotationMatrix(new THREE.Matrix4().makeBasis(x,y,z));
}
