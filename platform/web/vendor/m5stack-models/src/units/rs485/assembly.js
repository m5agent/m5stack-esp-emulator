import * as THREE from 'three';
import {Port,materials} from '../../core/index.js';
import {roundedRect} from '../../core/geometry.js';
import {slab,mesh} from '../../modeling/parts.js';

export function clearedBoard(host){
 const old=host.body.getObjectByName('Unit PCB');old.removeFromParent();old.geometry.dispose();old.material.dispose();
 const x=11.4,y=15.2,r=3.7,n=5.3,upper=8.3,s=new THREE.Shape();
 s.moveTo(-x+r,-y);s.lineTo(-n,-y);s.lineTo(-n,-9);s.lineTo(n,-9);s.lineTo(n,-y);s.lineTo(x-r,-y);
 const angle=Math.acos((upper-(x-r))/r),cornerY=y-r+r*Math.sin(angle);
 s.absarc(x-r,-y+r,r,-Math.PI/2,0);s.lineTo(x,y-r);s.absarc(x-r,y-r,r,0,angle);
 s.lineTo(upper,5.5);s.lineTo(-upper,5.5);s.lineTo(-upper,cornerY);
 s.absarc(-x+r,y-r,r,Math.PI-angle,Math.PI);s.lineTo(-x,-y+r);s.absarc(-x+r,-y+r,r,Math.PI,Math.PI*1.5);
 for(const cx of [-8,8])s.holes.push(roundedRect(6.2,6.2,3.1,{cx,cy:-4,path:new THREE.Path(),clockwise:true}));
 s.holes.push(roundedRect(3.8,3.8,1.9,{cx:0,cy:-4,path:new THREE.Path(),clockwise:true}));
 mesh(host.body,new THREE.ExtrudeGeometry(s,{depth:.8,bevelEnabled:false,curveSegments:16}),materials.plastic(0x2d493a,{roughness:.91}),[0,0,.1],'RS485 PCB with connector clearances');
}

export function terminal(host,spec){
 const group=new THREE.Group();group.name='RS485 fixed HT3.96-4P socket';host.body.add(group);
 const orange=materials.plastic(0xf49b39,{roughness:.67}),metal=materials.metal(0xb9bcb3,{roughness:.42});
 slab(group,15.8,9.8,.6,.3,[0,11.1,-.8],orange,[],.06).name='RS485 terminal floor';
 for(const x of [-7.55,7.55])slab(group,.7,9.8,6.4,.12,[x,11.1,-.2],orange,[],.04).name='RS485 terminal side wall';
 slab(group,14.4,.7,5.8,.12,[0,6.35,-.2],orange,[],.035).name='RS485 terminal rear wall';
 const windows=spec.terminal.pinX.map(cx=>({w:2.6,h:1.25,r:.12,cx,cy:-3.65}));
 const roof=slab(group,15.8,9.8,.65,.3,[0,11.1,5.55],orange,windows,.06);roof.name='RS485 terminal roof with inspection windows';
 for(const x of [-3.96,0,3.96])slab(group,.4,8.5,.7,.1,[x,11.7,-.2],orange,[],.035).name='RS485 terminal channel rib';
 for(const x of spec.terminal.pinX){
  mesh(group,new THREE.BoxGeometry(.68,8.4,.68),metal,[x,10.9,1.3],'RS485 terminal contact pin');
  mesh(group,new THREE.BoxGeometry(.68,1.9,.68),metal,[x,5.85,1.3],'RS485 terminal bent lead');
  mesh(group,new THREE.BoxGeometry(.68,.68,1.4),metal,[x,4.9,.6],'RS485 terminal PCB tail');
 }
 for(const x of [-7.0,7.0])slab(group,.7,1.1,.4,.1,[x,15.45,5.8],orange,[],.035).name='RS485 terminal retention ear';
 host.add(new Port({id:'terminal',label:'HT3.96-4P · RS485 and supply',connector:'ht3.96-4p',position:spec.terminal.position,hitSize:[15.8,1,7],pins:spec.terminal.names.map((name,i)=>({n:i+1,name})),pinGrid:{cols:4,rows:1,pitch:spec.terminal.pitch,center:[0,-1.4],order:col=>col+1},meta:{role:'visual-connector',face:'top',scope:'Physical connector and supplied removable accessory only; no UART, RS485, supply, wiring or electrical behavior'}}));
}
