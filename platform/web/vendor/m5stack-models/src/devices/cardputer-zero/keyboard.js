import * as THREE from 'three';
import {Button,materials,geometry} from '../../core/index.js';
import {slab,mesh} from '../../modeling/parts.js';
import {isolateActuatorMaterials} from '../../modeling/actuators.js';
import {DIM} from './dimensions.js';

export const KEY_CODES=[['F1','F2','F3','F4','F5','F6','F7','F8','F9','F10','Delete'],['Symbol','KeyQ','KeyW','KeyE','KeyR','KeyT','KeyY','KeyU','KeyI','KeyO','KeyP'],['ShiftLeft','KeyA','KeyS','KeyD','KeyF','KeyG','KeyH','KeyJ','KeyK','KeyL','Backspace'],['Fn','ControlLeft','AltLeft','KeyZ','KeyX','KeyC','KeyV','KeyB','KeyN','KeyM','Space']];
export function keyLayout(){
 const k=DIM.keyboard;
 return [...KEY_CODES.flatMap((row,r)=>row.map((id,c)=>({id,x:k.x0+c*k.dx,y:k.y0-r*k.dy}))),{id:'Escape',x:-37.8,y:2.55},{id:'Tab',x:37.8,y:2.55}];
}
export function addKeyboard(host,layout){
 const rubber=materials.plastic(0x171d1a,{roughness:.9}),well=materials.plastic(0x313a34,{roughness:.91});
 slab(host.body,80,31.2,.8,1.8,[0,-8.85,6.8],materials.plastic(0x284333,{roughness:.89}),[],.08).name='46-key matrix PCB';
 for(const {id,x,y}of layout){
  slab(host.body,5.55,3.2,1.3,1.35,[x,y,8.3],well,[],.08).name='Recessed key retaining well';
  const group=new THREE.Group();group.name=`Physical key ${id}`;
  mesh(group,geometry.roundedSlab({w:5.25,h:2.9,depth:DIM.keyboard.depth,radius:1.2,bevel:.38}),rubber,[0,0,0],'Rubber key cap');
  mesh(group,new THREE.CylinderGeometry(1.0,1.1,.7,16).rotateX(Math.PI/2),rubber,[0,0,-.25],'Key membrane stem');
  host.add(new Button({id:`key-${id}`,label:id,mesh:isolateActuatorMaterials(group),position:[x,y,DIM.keyboard.z],axis:[0,0,-1],travel:.25,meta:{role:'keyboard-key'}}));
 }
}
