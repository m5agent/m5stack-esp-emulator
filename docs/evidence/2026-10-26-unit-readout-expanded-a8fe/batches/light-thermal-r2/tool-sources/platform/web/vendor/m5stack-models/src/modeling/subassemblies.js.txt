import * as THREE from 'three';
import {materials} from '../core/materials.js';
import {slab,mesh} from './parts.js';

/** Physical StampS3A stack behind its artwork: board, package and edge contacts. */
export function stampS3A(parent,{x,y,front}){
 const group=new THREE.Group();group.position.set(x,y,front);parent.add(group);group.name='StampS3A physical board stack';
 slab(group,23.2,17.2,.8,.35,[0,0,-1.75],materials.plastic(0x29483b,{roughness:.9}),[],.05);
 slab(group,12.4,11.8,.95,.45,[-1.1,0,-.95],materials.metal(0x9ca3a0,{roughness:.55}),[],.08);
 for(const y of [-7.8,7.8])for(let i=0;i<9;i++)mesh(group,new THREE.BoxGeometry(1.1,1.5,.07),materials.metal(0xaa925b,{roughness:.5}),[(i-4)*2.54,y,-.91]);
 for(const x of [-10.9,10.9])for(let i=0;i<5;i++)mesh(group,new THREE.BoxGeometry(1.1,.9,.07),materials.metal(0xaa925b,{roughness:.5}),[x,(i-2)*2.54,-.91]);
 return group;
}
