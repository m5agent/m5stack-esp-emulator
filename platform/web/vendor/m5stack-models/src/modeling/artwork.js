import * as THREE from 'three';
import {FACE} from './parts.js';
import {DecalGeometry} from 'three/addons/geometries/DecalGeometry.js';
import {roundedRect} from '../core/geometry.js';

function rasterMaterial(host,url,panel,roughness){
 const material=new THREE.MeshStandardMaterial({color:0xffffff,roughness,metalness:0,transparent:true,opacity:0,alphaTest:.04,depthWrite:true,polygonOffset:true,polygonOffsetFactor:-2,polygonOffsetUnits:-2});
 if(typeof window!=='undefined'&&typeof document!=='undefined'&&typeof document.createElementNS==='function'){
  const texture=new THREE.TextureLoader().load(url,()=>{material.opacity=1;panel.userData.textureStatus='ready';host.requestRender();},undefined,()=>{panel.userData.textureStatus='error';host.requestRender();});
  texture.colorSpace=THREE.SRGBColorSpace;texture.anisotropy=8;material.map=texture;
 }
 return material;
}

/** A die-cut adhesive film where the official label itself bridges a recess. */
export function printedFilm(host,{url,size,position,face='front',rotation=0,parent=host.body,holes=[],name='Official adhesive film',roughness=.8,artworkKind='official-raster-film'}){
 if(host.options.artwork===false)return null;
 const shape=roundedRect(size[0],size[1],.05);
 for(const hole of holes)shape.holes.push(roundedRect(hole.w,hole.h,hole.r??Math.min(hole.w,hole.h)/2,{cx:hole.cx??0,cy:hole.cy??0,path:new THREE.Path(),clockwise:true}));
 const geometry=new THREE.ShapeGeometry(shape,32),positions=geometry.attributes.position,uv=geometry.attributes.uv;
 for(let i=0;i<uv.count;i++)uv.setXY(i,positions.getX(i)/size[0]+.5,positions.getY(i)/size[1]+.5);
 const panel=new THREE.Mesh(geometry,null);panel.name=name;panel.userData={role:'printed-artwork',artworkKind,textureStatus:'pending'};
 host.body.updateWorldMatrix(true,true);parent.updateWorldMatrix(true,false);
 const pose=new THREE.Matrix4().compose(new THREE.Vector3(...position),FACE[face].clone().multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1),rotation)),new THREE.Vector3(1,1,1));
 panel.applyMatrix4(parent.matrixWorld.clone().invert().multiply(host.body.matrixWorld).multiply(pose));
 panel.material=rasterMaterial(host,url,panel,roughness);parent.add(panel);return panel;
}

/**
 * Official raster artwork projected onto an explicit physical part. The
 * projection copies only existing surface triangles, so ports and cutouts stay
 * open. Children inherit the target's cap, lid or joint motion automatically.
 * Legacy photographic artwork below remains separately opt-in.
 */
export function printedArtwork(host,{target,url,size,position,face='front',rotation=0,depth=.3,name='Official printed sticker',roughness=.8,artworkKind='official-raster'}){
 if(host.options.artwork===false)return null;
 const targets=Array.isArray(target)?target:[target],panels=[];
 host.body.updateWorldMatrix(true,true);
 const localQuaternion=FACE[face].clone().multiply(new THREE.Quaternion().setFromAxisAngle(new THREE.Vector3(0,0,1),rotation));
 const quaternion=host.body.getWorldQuaternion(new THREE.Quaternion()).multiply(localQuaternion);
 const center=host.body.localToWorld(new THREE.Vector3(...position));
 const orientation=new THREE.Euler().setFromQuaternion(quaternion);
 const linear=new THREE.Matrix3().setFromMatrix4(host.body.matrixWorld);
 const scale=axis=>new THREE.Vector3(...axis).applyQuaternion(localQuaternion).applyMatrix3(linear).length();
 const volume=new THREE.Vector3(size[0]*scale([1,0,0]),size[1]*scale([0,1,0]),depth*scale([0,0,1]));
 const outward=new THREE.Vector3(0,0,1).applyQuaternion(quaternion);
 for(const source of targets){
  if(!source?.isMesh)throw new TypeError(`${name}: explicit surface mesh required`);
  source.updateWorldMatrix(true,false);
  const projected=new DecalGeometry(source,center,orientation,volume),keep=[],p=projected.attributes.position;
  const a=new THREE.Vector3(),b=new THREE.Vector3(),c=new THREE.Vector3();
  // A shallow projector may include the far side of a thin part. Print only
  // faces directed toward the label, never the underside or vertical walls.
  for(let i=0;i<p.count;i+=3){
   a.fromBufferAttribute(p,i);b.fromBufferAttribute(p,i+1).sub(a);c.fromBufferAttribute(p,i+2).sub(a);
   const normal=b.cross(c),area=normal.length();
   if(area>1e-12&&normal.dot(outward)>area*.05)keep.push(i,i+1,i+2);
  }
  if(!keep.length){projected.dispose();continue;}
  const geometry=new THREE.BufferGeometry();
  for(const [name,attribute]of Object.entries(projected.attributes)){
   const values=new Float32Array(keep.length*attribute.itemSize);
   for(let i=0;i<keep.length;i++)for(let k=0;k<attribute.itemSize;k++)values[i*attribute.itemSize+k]=attribute.array[keep[i]*attribute.itemSize+k];
   geometry.setAttribute(name,new THREE.BufferAttribute(values,attribute.itemSize));
  }
  projected.dispose();
  geometry.applyMatrix4(source.matrixWorld.clone().invert());
  const positions=geometry.attributes.position,normals=geometry.attributes.normal;
  for(let i=0;i<positions.count;i++){
   positions.setXYZ(i,positions.getX(i)+normals.getX(i)*.008,positions.getY(i)+normals.getY(i)*.008,positions.getZ(i)+normals.getZ(i)*.008);
  }
  geometry.computeBoundingBox();geometry.computeBoundingSphere();
  const panel=new THREE.Mesh(geometry,null);panel.name=name;panel.userData={role:'printed-artwork',artworkKind,surface:source.name,textureStatus:'pending'};
  panel.material=rasterMaterial(host,url,panel,roughness);
  source.add(panel);panels.push(panel);
 }
 if(!panels.length)throw new RangeError(`${name}: projector does not intersect its physical surface`);
 return panels;
}

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
