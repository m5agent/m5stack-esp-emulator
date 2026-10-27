import * as THREE from 'three';
import {materials,Port} from '../../core/index.js';
import {FACE,portQuaternion,mesh,slab} from '../../modeling/parts.js';

function ring(outer,inner){const shape=new THREE.Shape();shape.absarc(0,0,outer,0,Math.PI*2,false);const hole=new THREE.Path();hole.absarc(0,0,inner,0,Math.PI*2,true);shape.holes.push(hole);return shape;}
function tube(parent,outer,inner,depth,position,material,name){return mesh(parent,new THREE.ExtrudeGeometry(ring(outer,inner),{depth,bevelEnabled:false,curveSegments:48}),material,position,name);}

/** Board-edge MMCX and tripod inserts omitted from the enclosure STL. */
export function addEdgeDetails(host){
 const brass=materials.metal(0xb79c47,{roughness:.42}),insulator=materials.plastic(0xe3dfcf,{roughness:.76});
 for(const [i,x]of [-48,1].entries()){
  const g=new THREE.Group();g.position.set(x,40.02,-1.6);g.quaternion.copy(FACE.top);g.name=`MMCX antenna socket ${i+1}`;g.userData.role='visual-connector';host.body.add(g);
  tube(g,2.05,1.25,3.7,[0,0,-3.6],brass,'MMCX outer sleeve');
  tube(g,1.23,.42,.7,[0,0,-1.25],insulator,'MMCX dielectric seat');
  tube(g,.4,.22,.9,[0,0,-1.15],brass,'MMCX center receptacle');
  mesh(g,new THREE.CylinderGeometry(1.24,1.24,.18,32).rotateX(Math.PI/2),materials.plastic(0x161b14),[0,0,-3.6],'MMCX internal backstop');
  host.add(new Port({id:`mmcx-${i+1}`,label:`MMCX antenna ${i+1}`,connector:'mmcx',position:g.position.toArray(),quaternion:portQuaternion('top'),hitSize:[4.1,1,4.1],meta:{role:'visual-connector',face:'top'}}));
 }
 const mount=new THREE.Group();mount.position.set(0,-40.02,.3);mount.quaternion.copy(FACE.bottom);mount.name='Quarter-inch tripod insert';mount.userData={role:'mounting-insert',nominalThread:'1/4-20'};host.body.add(mount);
 tube(mount,4.15,3.175,4.7,[0,0,-4.55],brass,'Tripod brass body');
 const curve=new THREE.CatmullRomCurve3(Array.from({length:161},(_,i)=>{const a=i/160*Math.PI*2*3.3;return new THREE.Vector3(3.13*Math.cos(a),3.13*Math.sin(a),-.25-i/160*4.19);}));
 mesh(mount,new THREE.TubeGeometry(curve,200,.14,8,false),brass,[0,0,0],'Tripod internal helical thread');
 mesh(mount,new THREE.CylinderGeometry(3.2,3.2,.2,48).rotateX(Math.PI/2),materials.plastic(0x161b18,{roughness:.95}),[0,0,-4.65],'Tripod blind-hole floor');
 const acoustic=new THREE.Group();acoustic.position.set(36.5,-38.8,.2);acoustic.quaternion.copy(FACE.bottom);acoustic.name='Long-edge speaker acoustic housing';host.body.add(acoustic);
 slab(acoustic,25,8,1.2,1,[0,0,-1.2],materials.plastic(0x111614,{roughness:1}),[],.06).name='Speaker grille backing';
}
