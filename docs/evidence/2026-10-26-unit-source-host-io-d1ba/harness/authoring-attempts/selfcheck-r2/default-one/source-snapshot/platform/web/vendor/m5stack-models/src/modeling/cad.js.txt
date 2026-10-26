import * as THREE from 'three';
import {materials} from '../core/materials.js';
const colors={black:0x24272a,light:0xcaced0,cyan:0x05a9c6,yellow:0xf2be18,blue:0x197cb8,red:0xbe3a28};
function decode(s,Type){const binary=atob(s),bytes=new Uint8Array(binary.length);for(let i=0;i<binary.length;i++)bytes[i]=binary.charCodeAt(i);return new Type(bytes.buffer);}
/** Construct independent geometry objects from the selected official assembly components. */
export function addCadParts(host,data,palette={}){
 const parts={};for(const part of data){const g=new THREE.BufferGeometry();g.setAttribute('position',new THREE.BufferAttribute(decode(part.position,Float32Array),3));g.setAttribute('normal',new THREE.BufferAttribute(decode(part.normal,Float32Array),3));g.setIndex(new THREE.BufferAttribute(decode(part.index,Uint32Array),1));g.computeBoundingBox();const material=palette[part.material]??materials.plastic(colors[part.material]??0xdddddd,{roughness:.7,clearcoat:.02});const mesh=new THREE.Mesh(g,material);mesh.name=part.name;mesh.userData.source='official-structure';host.body.add(mesh);parts[part.name]=mesh;}host.parts=parts;return parts;
}
