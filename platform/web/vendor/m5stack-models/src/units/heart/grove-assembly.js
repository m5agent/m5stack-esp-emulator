import * as THREE from 'three';
import {roundedRect} from '../../core/geometry.js';
import {mesh} from '../../modeling/parts.js';
import {refineOpenTopGrove} from '../shared/open-top-grove.js';

export function addHeartGrove(host){
 const old=host.body.getObjectByName('Unit PCB');
 if(!old?.isMesh)throw new Error('Heart requires its original PCB before Grove clearance');
 // Preserve the board's thickness, seat and two mounting bores. The open
 // edge notch is inferred from the real connector bay, not a fabricated hole
 // intersecting the outline or a translation of the complete PCB.
 const x=11.4,y=15.2,r=3.7,n=5.3,notchEnd=-8.85,s=new THREE.Shape();
 s.moveTo(-x+r,-y);s.lineTo(-n,-y);s.lineTo(-n,notchEnd);s.lineTo(n,notchEnd);s.lineTo(n,-y);s.lineTo(x-r,-y);
 s.absarc(x-r,-y+r,r,-Math.PI/2,0);s.lineTo(x,y-r);s.absarc(x-r,y-r,r,0,Math.PI/2);
 s.lineTo(-x+r,y);s.absarc(-x+r,y-r,r,Math.PI/2,Math.PI);s.lineTo(-x,-y+r);s.absarc(-x+r,-y+r,r,Math.PI,Math.PI*1.5);s.closePath();
 for(const cx of [-8,8])s.holes.push(roundedRect(6.2,6.2,3.1,{cx,cy:-4,path:new THREE.Path(),clockwise:true}));
 const position=old.position.clone(),material=old.material;
 old.removeFromParent();old.geometry.dispose();
 const board=mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:24}),material,position.toArray(),'Heart PCB with Grove clearance');
 host.heartGroveBoard=board;
 refineOpenTopGrove(host,'heart');
}
