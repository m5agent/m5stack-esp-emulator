import * as THREE from 'three';
import {materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {mesh,FACE} from '../../modeling/parts.js';

export function motorBoard(host){
 const old=host.body.getObjectByName('Unit PCB');old.removeFromParent();old.geometry.dispose();old.material.dispose();
 const x=11.4,y=15.2,r=3.7,n=5.3,upper=5.6,s=new THREE.Shape();
 s.moveTo(-x+r,-y);s.lineTo(-n,-y);s.lineTo(-n,-9);s.lineTo(n,-9);s.lineTo(n,-y);s.lineTo(x-r,-y);
 s.absarc(x-r,-y+r,r,-Math.PI/2,0);s.lineTo(x,y-r);s.absarc(x-r,y-r,r,0,Math.PI/2);
 s.lineTo(upper,y);s.lineTo(upper,-1);s.lineTo(-upper,-1);s.lineTo(-upper,y);
 s.lineTo(-x+r,y);s.absarc(-x+r,y-r,r,Math.PI/2,Math.PI);s.lineTo(-x,-y+r);s.absarc(-x+r,-y+r,r,Math.PI,Math.PI*1.5);
 for(const cx of [-8,8])s.holes.push(roundedRect(6.2,6.2,3.1,{cx,cy:-4,path:new THREE.Path(),clockwise:true}));
 s.holes.push(roundedRect(3.8,3.8,1.9,{cx:0,cy:-4,path:new THREE.Path(),clockwise:true}));
 mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:16}),materials.plastic(0x2d493a,{roughness:.91}),[0,0,.1],'Fan PCB with motor and Grove clearances');
}

export function motor(host,spec){
 const silver=materials.metal(0xa9afaa,{roughness:.48});
 mesh(host.body,new THREE.CylinderGeometry(4.75,4.75,14.5,48),silver,[0,7.95,2],'Fan motor can');
 const bearing=new THREE.Shape();bearing.absarc(0,0,2.35,0,Math.PI*2,false);const hole=new THREE.Path();hole.absarc(0,0,.53,0,Math.PI*2,true);bearing.holes.push(hole);
 const cap=mesh(host.body,new THREE.ExtrudeGeometry(bearing,{depth:.35,bevelEnabled:false,curveSegments:40}),silver,[0,15.3,2],'Fan recessed bearing');cap.quaternion.copy(FACE.top);
 mesh(host.body,new THREE.CylinderGeometry(.5,.5,3.4,32),silver,[0,16.9,spec.shaft.centerZ],'Fan motor shaft');
}

export function propeller(host,spec){
 const group=new THREE.Group();group.name='Optional static 60 mm propeller';group.position.set(0,spec.propeller.centerY,spec.shaft.centerZ);host.body.add(group);
 const black=materials.plastic(0x181b1c,{roughness:.6});
 const ring=new THREE.Shape();ring.absarc(0,0,2.7,0,Math.PI*2,false);const bore=new THREE.Path();bore.absarc(0,0,.5,0,Math.PI*2,true);ring.holes.push(bore);
 const hub=mesh(group,new THREE.ExtrudeGeometry(ring,{depth:1.9,bevelEnabled:false,curveSegments:40}),black,[0,-.95,0],'Fan propeller bored hub');hub.quaternion.copy(FACE.top);
 // A static, double-bladed airfoil. Diameter is official; blade chord, twist and
 // hub packaging follow the product photographs and are not an aerodynamic model.
 for(const sign of [-1,1]){
  const positions=[],indices=[],rows=22,columns=6,count=(rows+1)*(columns+1);
  for(const thickness of [-.18,.18])for(let i=0;i<=rows;i++){const t=i/rows,r=2.2+27.8*t,chord=1.8+2.5*Math.sin(Math.PI*t*.9);for(let j=0;j<=columns;j++){const q=j/columns-.5;positions.push(sign*r,q*(1.7-.8*t)+thickness,sign*(q*chord*2+.6*Math.sin(Math.PI*t)));}}
  for(let i=0;i<rows;i++)for(let j=0;j<columns;j++){const a=i*(columns+1)+j,b=a+columns+1;indices.push(a,b,a+1,b,b+1,a+1,a+count,a+1+count,b+count,b+count,a+1+count,b+1+count);}
  const edge=[];for(let j=0;j<=columns;j++)edge.push(j);for(let i=1;i<=rows;i++)edge.push(i*(columns+1)+columns);for(let j=columns-1;j>=0;j--)edge.push(rows*(columns+1)+j);for(let i=rows-1;i>0;i--)edge.push(i*(columns+1));
  for(let i=0;i<edge.length;i++){const a=edge[i],b=edge[(i+1)%edge.length];indices.push(a,a+count,b,b,a+count,b+count);}
  const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.Float32BufferAttribute(positions,3));g.setIndex(indices);g.computeVertexNormals();
  mesh(group,g,black.clone(),[0,0,0],'Fan propeller blade');
 }
}
