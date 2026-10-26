import * as THREE from 'three';
import {FACE} from './parts.js';

/** A printed surface from a documented official photograph. Geometry stays independent. */
export function artwork(host,{url,size,position,face='front',name='printed artwork',roughness=.82}){
 // Photographic sticker crops are disabled by default. Await original artwork files.
 if(host.options.artwork!==true)return null;
 const material=new THREE.MeshStandardMaterial({color:0xffffff,roughness,metalness:0,transparent:true,polygonOffset:true,polygonOffsetFactor:-1,polygonOffsetUnits:-1});
 const panel=new THREE.Mesh(new THREE.PlaneGeometry(...size),material);
 panel.name=name;panel.position.fromArray(position);panel.quaternion.copy(FACE[face]);
 panel.userData.role='printed-artwork';host.body.add(panel);
 // Geometry/API checks run without a DOM image decoder. Pixel acceptance is a separate browser gate.
 if(typeof window!=='undefined'){
  const texture=new THREE.TextureLoader().load(url,()=>host.requestRender());
  texture.colorSpace=THREE.SRGBColorSpace;texture.anisotropy=8;material.map=texture;
 }
 return panel;
}
